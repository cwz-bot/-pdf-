import streamlit as st
import fitz  # PyMuPDF
import numpy as np
from PIL import Image
import io
import google.generativeai as genai
import re
import time
import zipfile

# 頁面配置
st.set_page_config(page_title="鐵路安衛文件助手", page_icon="🚉", layout="wide")

st.title("🚉 鐵路安衛文件 - 智慧辨識與去空白工具")
st.markdown("""
本工具將自動執行：
1. **AI 視覺辨識**：讀取第一頁手寫內容，自動生成檔名（民國轉西元）。
2. **自動去空白**：偵測並移除背面空白頁。
3. **打包下載**：處理完成後統一打包為 ZIP 檔。
""")

# 側邊欄設定
with st.sidebar:
    st.header("🔑 API 設定")
    api_key = st.text_input("請輸入 Gemini API Key", type="password")
    st.info("免費 API Key 可至 [Google AI Studio](https://aistudio.google.com/) 申請")
    
    st.header("⚙️ 辨識偏好")
    model_choice = st.selectbox("選擇模型", ["gemini-1.5-flash", "gemini-1.5-pro"], index=0)
    st.caption("Flash 速度快、穩定；Pro 辨識力最強但限制較多。")

# --- 核心函數 ---

def is_blank_page(page, threshold=0.01):
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    img = Image.open(io.BytesIO(pix.tobytes())).convert('L')
    img_array = np.array(img)
    non_white_pixels = np.sum(img_array < 250)
    return (non_white_pixels / img_array.size) < threshold

def get_smart_name(model, img):
    prompt = """
    你現在是精密的鐵路文件解析員。請閱讀圖片並提取資訊：
    1. 【日期】：找到民國年份(如114)，換算西元(民國+1911)。格式 YYYYMMDD。
    2. 【車站】：提取括號()內的文字，並加上"車站"二字。
    3. 【項目】：提取括號以外的核心描述。
    輸出格式：YYYYMMDD_車站_項目
    """
    try:
        response = model.generate_content([prompt, img])
        return re.sub(r'[\\/:*?"<>|]', '', response.text.strip().split('\n')[0])
    except Exception as e:
        st.error(f"AI 辨識出錯: {e}")
        return None

# --- 主程式介面 ---

uploaded_files = st.file_uploader("📤 請拖入 PDF 檔案 (可多選)", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if not api_key:
        st.warning("⚠️ 請先在左側輸入 API Key 才能開始辨識。")
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_choice)
        
        if st.button("🚀 開始批次處理"):
            processed_files = [] # 儲存處理後的二進位資料與檔名
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for index, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"正在處理 ({index+1}/{len(uploaded_files)}): {uploaded_file.name}")
                
                # 讀取 PDF
                file_bytes = uploaded_file.read()
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                
                # 1. AI 辨識檔名
                pix = doc[0].get_pixmap(matrix=fitz.Matrix(3, 3))
                img = Image.open(io.BytesIO(pix.tobytes()))
                new_base_name = get_smart_name(model, img) or uploaded_file.name.replace(".pdf", "")
                
                # 2. 去空白邏輯
                new_doc = fitz.open()
                for i in range(len(doc)):
                    if i % 2 == 0: # 正面
                        new_doc.insert_pdf(doc, from_page=i, to_page=i)
                    else: # 背面
                        if not is_blank_page(doc[i]):
                            new_doc.insert_pdf(doc, from_page=i, to_page=i)
                
                # 儲存到記憶體
                out_buffer = io.BytesIO()
                new_doc.save(out_buffer)
                processed_files.append((f"{new_base_name}.pdf", out_buffer.getvalue()))
                
                doc.close()
                new_doc.close()
                
                # 更新進度
                progress_bar.progress((index + 1) / len(uploaded_files))
                # 避免 429 錯誤的短暫休息
                time.sleep(1.5 if model_choice == "gemini-1.5-flash" else 15)

            status_text.success("✅ 全部檔案處理完成！")
            
            # 3. 打包 ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                for file_name, data in processed_files:
                    zip_file.writestr(file_name, data)
            
            st.download_button(
                label="📂 下載所有處理完成的檔案 (ZIP)",
                data=zip_buffer.getvalue(),
                file_name="processed_documents.zip",
                mime="application/zip"
            )

# --- 部署提示 ---
with st.expander("ℹ️ 如何部署到 Streamlit Cloud?"):
    st.write("""
    1. 將此程式碼存為 `app.py`。
    2. 建立一個 `requirements.txt` 檔案，內容如下：
       ```
       streamlit
       pymupdf
       numpy
       pillow
       google-generativeai
       ```
    3. 將兩個檔案上傳至 GitHub Repo。
    4. 登入 [Streamlit Cloud](https://share.streamlit.io/) 並連結該 Repo 即可。
    """)