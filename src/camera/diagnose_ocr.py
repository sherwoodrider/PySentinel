import sys
import cv2
import numpy as np
from PIL import Image
import pytesseract


def diagnose_ocr():
    print("=" * 60)
    print("OCR 诊断工具")
    print("=" * 60)

    # 1. 检查Python环境
    print(f"Python版本: {sys.version}")

    # 2. 检查OpenCV
    print(f"OpenCV版本: {cv2.__version__}")

    # 3. 检查PIL
    print(f"PIL版本: {Image.__version__ if hasattr(Image, '__version__') else 'N/A'}")

    # 4. 检查Tesseract
    try:
        print(f"Tesseract版本: {pytesseract.get_tesseract_version()}")
    except:
        print("❌ Tesseract未找到或配置错误")
        print("请设置路径: pytesseract.pytesseract.tesseract_cmd = r'路径\\tesseract.exe'")
        return

    # 5. 创建测试图像
    print("\n创建测试图像...")
    img_array = np.zeros((100, 400, 3), dtype=np.uint8)

    # 添加文本
    cv2.putText(img_array, "中文", (50, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(img_array, "Test", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    # 转换为PIL图像
    pil_img = Image.fromarray(cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB))

    # 6. 测试识别
    print("\n测试识别...")

    # 测试英文
    try:
        eng_text = pytesseract.image_to_string(pil_img, lang='eng')
        print(f"✅ 英文识别: '{eng_text.strip()}'")
    except Exception as e:
        print(f"❌ 英文识别失败: {e}")

    # 测试中文
    try:
        chi_text = pytesseract.image_to_string(pil_img, lang='chi_sim')
        print(f"✅ 中文识别: '{chi_text.strip()}'")
    except Exception as e:
        print(f"❌ 中文识别失败: {e}")
        print("可能原因:")
        print("  1. 中文语言包未安装")
        print("  2. Tesseract路径不正确")

    # 7. 列出所有语言
    try:
        langs = pytesseract.get_languages()
        print(f"\n可用语言: {langs}")
    except:
        pass

    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)


if __name__ == "__main__":
    diagnose_ocr()