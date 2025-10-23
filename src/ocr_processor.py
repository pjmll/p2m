#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR处理模块
使用大模型接口对扫描版PDF进行文本识别
"""

import base64
import os
from io import BytesIO
from typing import List, Optional

import fitz  # PyMuPDF
from PIL import Image
from openai import OpenAI

from src.service.logger import logger


class OCRProcessor:
    """OCR处理器，基于多模态大模型完成OCR识别"""

    def __init__(
        self,
        dpi: int = 300,
        model: Optional[str] = None,
        prompt: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
    ):
        self.dpi = dpi
        self.model = (
            model
            or os.getenv("OCR_MODEL")
            or os.getenv("OPENAI_MODEL")
            or "qwen3-vl-plus"
        )

        api_key = (
            os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("AZURE_OPENAI_KEY")
        )
        if not api_key:
            raise RuntimeError("未找到大模型 API Key，请设置 DASHSCOPE_API_KEY 或 OPENAI_API_KEY")

        base_url = (
            os.getenv("DASHSCOPE_API_URL")
            or os.getenv("OPENAI_BASE_URL")
            or os.getenv("AZURE_OPENAI_BASE_URL")
        )

        if base_url:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self.client = OpenAI(api_key=api_key)

        self.prompt_template = (
            prompt
            or os.getenv("OCR_PROMPT")
            or "You are an OCR engine. Extract every piece of legible text from the image in its original language ({lang}). Preserve reading order and use blank lines between paragraphs when necessary."
        )
        self.system_prompt = os.getenv(
            "OCR_SYSTEM_PROMPT",
            "You transcribe document images without adding explanations.",
        )
        self.max_output_tokens = max_output_tokens or int(
            os.getenv("OCR_MAX_OUTPUT_TOKENS", "4096")
        )

    def process_pdf(self, pdf_path: str, lang: str = "auto") -> str:
        logger.info("开始调用大模型进行OCR: %s", pdf_path)

        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            logger.info("PDF总页数: %d", total_pages)

            all_text: List[str] = []

            for page_num in range(total_pages):
                logger.info("处理第 %d/%d 页", page_num + 1, total_pages)

                page = doc.load_page(page_num)
                matrix = fitz.Matrix(self.dpi / 72, self.dpi / 72)
                pix = page.get_pixmap(matrix=matrix)
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                page_text = self._ocr_image(image, lang)

                if page_text.strip():
                    all_text.append(f"=== 第 {page_num + 1} 页 ===\n{page_text.strip()}\n")
                else:
                    all_text.append(f"=== 第 {page_num + 1} 页 ===\n[无文本内容]\n")

            doc.close()

            combined = "\n".join(all_text)
            logger.info("OCR处理完成，共提取 %d 个字符", len(combined))
            return combined

        except Exception as exc:
            logger.error("OCR处理失败: %s", exc)
            raise

    def process_single_page(self, pdf_path: str, page_num: int, lang: str = "auto") -> str:
        try:
            doc = fitz.open(pdf_path)
            page = doc.load_page(page_num)

            matrix = fitz.Matrix(self.dpi / 72, self.dpi / 72)
            pix = page.get_pixmap(matrix=matrix)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            text = self._ocr_image(image, lang)

            doc.close()
            return text

        except Exception as exc:
            logger.error("处理第 %d 页失败: %s", page_num, exc)
            return ""

    def extract_blocks(self, image: Image.Image, lang: str = "auto") -> List[str]:
        text = self._ocr_image(image, lang)
        if not text.strip():
            return []

        separator = "\n\n" if "\n\n" in text else "\n"
        blocks = [block.strip() for block in text.split(separator) if block.strip()]
        return blocks

    def _format_prompt(self, lang: str) -> str:
        try:
            return self.prompt_template.format(lang=lang)
        except Exception:
            return self.prompt_template

    def _ocr_image(self, image: Image.Image, lang: str) -> str:
        try:
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

            user_content = [
                {"type": "text", "text": self._format_prompt(lang)},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                },
            ]

            messages = [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": self.system_prompt}],
                },
                {"role": "user", "content": user_content},
            ]

            response_text = self._call_model(messages)
            return response_text.strip()

        except Exception as exc:
            logger.error("图像OCR识别失败: %s", exc)
            return ""

    def _call_model(self, messages) -> str:
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_output_tokens,
        )
        return self._extract_text_from_completion(completion)

    @staticmethod
    def _extract_text_from_response(response) -> str:
        if hasattr(response, "output_text") and response.output_text:
            return response.output_text

        try:
            data = response.model_dump()
        except AttributeError:
            data = response

        if not isinstance(data, dict):
            return ""

        if data.get("output_text"):
            return data["output_text"]

        outputs = data.get("output") or []
        texts: List[str] = []
        for item in outputs:
            for content in item.get("content", []):
                text = content.get("text") or content.get("value")
                if text:
                    texts.append(text)

        return "\n".join(texts)

    @staticmethod
    def _extract_text_from_completion(completion) -> str:
        if hasattr(completion, "choices"):
            choice = completion.choices[0]
            content = getattr(choice.message, "content", None)
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                texts: List[str] = []
                for item in content:
                    text = None
                    if isinstance(item, dict):
                        text = item.get("text") or item.get("value")
                    else:
                        text = getattr(item, "text", None)
                    if text:
                        texts.append(text)
                if texts:
                    return "\n".join(texts).strip()

        try:
            data = completion.model_dump()
        except AttributeError:
            data = completion

        if isinstance(data, dict):
            choices = data.get("choices") or []
            if choices:
                message = choices[0].get("message", {})
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip()
                if isinstance(content, list):
                    texts = []
                    for item in content:
                        text = item.get("text") or item.get("value")
                        if text:
                            texts.append(text)
                    if texts:
                        return "\n".join(texts).strip()

        return ""
