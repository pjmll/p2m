#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR处理模块
使用Tesseract进行扫描版PDF的文本识别
"""

import os
import sys
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from io import BytesIO
import pandas as pd
from typing import List, Tuple

class OCRProcessor:
    """OCR处理器，专门处理扫描版PDF"""
    
    def __init__(self, dpi: int = 300):
        """
        初始化OCR处理器
        
        Args:
            dpi: 图像DPI，越高识别精度越好但处理时间越长
        """
        self.dpi = dpi
        
        # 检查Tesseract是否可用
        try:
            pytesseract.get_tesseract_version()
        except Exception as e:
            print(f"警告：Tesseract OCR未正确安装: {e}")
            print("请确保已安装Tesseract OCR")
    
    def process_pdf(self, pdf_path: str, lang: str = 'eng') -> str:
        """
        处理PDF文件，提取所有页面的文本
        
        Args:
            pdf_path: PDF文件路径
            lang: OCR语言，如'eng', 'chi_sim', 'eng+chi_sim'等
            
        Returns:
            提取的文本内容
        """
        print(f"开始OCR处理PDF: {pdf_path}")
        print(f"使用语言: {lang}")
        
        try:
            # 打开PDF文档
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            print(f"PDF总页数: {total_pages}")
            
            all_text = []
            
            for page_num in range(total_pages):
                print(f"处理第 {page_num + 1}/{total_pages} 页...")
                
                # 获取页面
                page = doc.load_page(page_num)
                
                # 转换为高分辨率图像
                matrix = fitz.Matrix(self.dpi/72, self.dpi/72)
                pix = page.get_pixmap(matrix=matrix)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # OCR识别
                page_text = self._ocr_image(img, lang)
                
                if page_text.strip():
                    all_text.append(f"=== 第 {page_num + 1} 页 ===\n{page_text}\n")
                else:
                    all_text.append(f"=== 第 {page_num + 1} 页 ===\n[无文本内容]\n")
            
            doc.close()
            
            # 合并所有文本
            full_text = "\n".join(all_text)
            print(f"OCR处理完成，共提取 {len(full_text)} 个字符")
            
            return full_text
            
        except Exception as e:
            print(f"OCR处理失败: {e}")
            raise
    
    def _ocr_image(self, image: Image.Image, lang: str) -> str:
        """
        对单个图像进行OCR识别
        
        Args:
            image: PIL图像对象
            lang: OCR语言
            
        Returns:
            识别的文本
        """
        try:
            # 使用公开方法获取详细的OCR数据（DataFrame）
            ocr_data = self.image_to_data_df(image, lang=lang)

            # 按块和段落分组
            grouped = ocr_data.groupby(['block_num', 'par_num']) if not ocr_data.empty else []

            text_blocks = []

            for (block_num, par_num), group in grouped:
                if group.empty or group['text'].str.strip().eq('').all():
                    continue

                # 合并文本
                text = ' '.join(group['text'].astype(str))
                text = text.strip()

                if text:
                    text_blocks.append(text)

            # 合并所有文本块
            result = '\n'.join(text_blocks)

            return result
            
        except Exception as e:
            print(f"图像OCR识别失败: {e}")
            return ""
    
    def process_single_page(self, pdf_path: str, page_num: int, lang: str = 'eng') -> str:
        """
        处理PDF的单个页面
        
        Args:
            pdf_path: PDF文件路径
            page_num: 页面编号（从0开始）
            lang: OCR语言
            
        Returns:
            该页面的文本内容
        """
        try:
            doc = fitz.open(pdf_path)
            page = doc.load_page(page_num)
            
            # 转换为图像
            matrix = fitz.Matrix(self.dpi/72, self.dpi/72)
            pix = page.get_pixmap(matrix=matrix)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # OCR识别
            text = self._ocr_image(img, lang)
            
            doc.close()
            return text
            
        except Exception as e:
            print(f"处理第{page_num}页失败: {e}")
            return ""
    
    def get_available_languages(self) -> List[str]:
        """
        获取可用的OCR语言列表
        
        Returns:
            可用语言列表
        """
        try:
            langs = pytesseract.get_languages()
            return langs
        except Exception as e:
            print(f"获取语言列表失败: {e}")
            return ['eng']  # 默认返回英语

    def image_to_data_df(self, image: Image.Image, lang: str = 'eng') -> 'pd.DataFrame':
        """
        返回 pytesseract.image_to_data 的 DataFrame 结果并做基础清洗（conf 转为数值并过滤阈值）。

        Args:
            image: PIL 图像对象
            lang: OCR 语言

        Returns:
            过滤后的 pandas.DataFrame（如果出错则返回空 DataFrame）
        """
        try:
            df = pytesseract.image_to_data(
                image,
                output_type=pytesseract.Output.DATAFRAME,
                lang=lang
            )

            # 确保 conf 为数值类型
            if 'conf' in df.columns:
                df['conf'] = pd.to_numeric(df['conf'], errors='coerce').fillna(-1)
            else:
                df['conf'] = -1

            # 过滤掉可信度低的结果
            filtered = df[df['conf'] > 60]
            return filtered
        except Exception as e:
            print(f"image_to_data_df 失败: {e}")
            # 返回一个空的 DataFrame，列与 pytesseract 输出相似
            cols = ['level','page_num','block_num','par_num','line_num','word_num','left','top','width','height','conf','text']
            return pd.DataFrame(columns=cols)
