# 导入库
from camera_utils import CameraUtils
import cv2
import os


def main():
    # 创建实例
    camera = CameraUtils()

    # 图像路径
    image_path = "./1.jpg"

    # 检查图像是否存在
    if not os.path.exists(image_path):
        print(f"❌ 图像文件不存在: {image_path}")

        # 创建测试图像
        print("创建测试图像...")
        import numpy as np
        test_img = np.zeros((400, 600, 3), dtype=np.uint8)
        test_img.fill(240)

        # 添加中英文混合文本（更好的测试）
        text_lines = [
            "中文OCR测试示例 Chinese Test",
            "Python OpenCV Tesseract EasyOCR",
            "请选择要识别的区域 Select ROI",
            "区域选择后按Enter确认 Press Enter",
            "测试文本 123 ABC 456 DEF"
        ]

        y = 80
        for i, line in enumerate(text_lines):
            font_scale = 1.2 if i == 0 else 0.8
            color = (0, 100, 200) if i == 0 else (0, 0, 0)
            thickness = 3 if i == 0 else 2

            cv2.putText(test_img, line, (50, y),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)
            y += 60

        cv2.imwrite(image_path, test_img)
        print(f"✅ 已创建测试图像: {image_path}")

    # 读取图像
    print(f"读取图像: {image_path}")
    original_image = camera.read_image(image_path)

    if original_image is None:
        print("❌ 无法读取图像")
        return

    print(f"✅ 图像加载成功，尺寸: {original_image.shape}")

    # 显示原始图像
    cv2.imshow("原始图像 (按任意键继续)", original_image)
    cv2.waitKey(0)
    cv2.destroyWindow("原始图像 (按任意键继续)")

    # ============ 选择OCR引擎 ============
    print("\n" + "=" * 60)
    print("请选择OCR引擎:")
    print("=" * 60)
    print("1. Tesseract (传统引擎，已配置)")
    print("2. EasyOCR (深度学习引擎，需要额外安装)")
    print("3. 两种引擎都使用 (对比结果)")

    ocr_choice = input("请输入选择 (1/2/3, 默认1): ").strip()
    use_tesseract = ocr_choice in ['1', '3', '']
    use_easyocr = ocr_choice in ['2', '3']

    if use_easyocr:
        # 尝试导入EasyOCR
        try:
            import easyocr
            print("✅ EasyOCR 可用")
        except ImportError:
            print("❌ EasyOCR 未安装，无法使用此引擎")
            print("请运行: pip install easyocr")
            use_easyocr = False
            if not use_tesseract:
                use_tesseract = True  # 回退到Tesseract

    # ============ 选择ROI区域 ============
    print("\n" + "=" * 60)
    print("请用鼠标选择识别区域")
    print("=" * 60)
    print("1. 拖拽鼠标绘制矩形框")
    print("2. 按 Enter 确认选择")
    print("3. 按 ESC 取消选择（使用全图）")
    print("=" * 60)

    roi = camera.select_roi_interactive(original_image)

    # ============ 执行OCR识别 ============
    print("\n" + "=" * 60)
    print("开始OCR识别...")
    print("=" * 60)

    results = []

    # Tesseract 识别
    if use_tesseract:
        print("\n📋 使用 Tesseract 识别...")

        # 选择语言
        print("请选择语言:")
        print("1. 简体中文 (chi_sim)")
        print("2. 英文 (eng)")
        print("3. 中英文混合 (chi_sim+eng)")
        lang_choice = input("请输入选择 (1/2/3, 默认1): ").strip()

        lang_map = {
            '1': 'chi_sim',
            '2': 'eng',
            '3': 'chi_sim+eng'
        }

        lang = lang_map.get(lang_choice, 'chi_sim')
        print(f"使用语言: {lang}")

        # 识别ROI区域
        result = camera.recognize_chinese_text_in_roi(original_image, roi, lang=lang)

        # 添加引擎信息
        result['engine'] = 'Tesseract'
        result['language'] = lang
        results.append(result)

        print(f"✅ Tesseract 识别完成")

    # EasyOCR 识别
    if use_easyocr:
        print("\n📋 使用 EasyOCR 识别...")

        # 选择语言模式
        print("请选择语言模式:")
        print("1. 简体中文 (ch_sim)")
        print("2. 中英文混合 (ch_sim+en)")
        print("3. 英文 (en)")
        mode_choice = input("请输入选择 (1/2/3, 默认2): ").strip()

        mode_map = {
            '1': ['ch_sim'],
            '2': ['ch_sim', 'en'],
            '3': ['en']
        }

        lang_list = mode_map.get(mode_choice, ['ch_sim', 'en'])
        print(f"使用语言: {lang_list}")

        # 选择是否使用GPU
        use_gpu_input = input("是否使用GPU加速? (y/n, 默认n): ").strip().lower()
        use_gpu = use_gpu_input == 'y'

        # 提取ROI区域
        roi_image = camera.extract_roi(original_image, roi) if roi else original_image

        # 使用EasyOCR识别
        if len(lang_list) == 1 and lang_list[0] == 'ch_sim':
            # 纯中文识别
            result = camera.recognize_chinese_easyocr(roi_image, gpu=use_gpu)
        else:
            # 混合语言识别
            result = camera.recognize_text_easyocr(roi_image, lang_list=lang_list, gpu=use_gpu)

        # 添加引擎信息
        result['engine'] = 'EasyOCR'
        result['language'] = lang_list
        result['gpu'] = use_gpu
        results.append(result)

        print(f"✅ EasyOCR 识别完成")

    # ============ 显示结果 ============
    print("\n" + "=" * 60)
    print("OCR 识别结果:")
    print("=" * 60)

    best_result = None
    best_confidence = 0

    for i, result in enumerate(results):
        print(f"\n🔍 引擎: {result.get('engine', 'Unknown')}")
        print(f"🌐 语言: {result.get('language', 'N/A')}")

        if result.get("error"):
            print(f"❌ 识别错误: {result['error']}")
        else:
            print(f"📝 识别文本: {result['text']}")
            print(f"📊 置信度: {result['confidence']:.2f}%")
            print(f"🔢 单词数量: {result['word_count']}")

            # 记录最佳结果
            if result['confidence'] > best_confidence:
                best_confidence = result['confidence']
                best_result = result

            # 显示前5个单词的详细信息
            if 'words_info' in result and result['words_info']:
                print(f"\n🔍 检测到的单词 (前5个):")
                for j, word_info in enumerate(result['words_info'][:5]):
                    text_display = word_info['text'] if len(word_info['text']) <= 20 else word_info['text'][:20] + "..."
                    print(f"  {j + 1}. '{text_display}' - 置信度: {word_info['confidence']:.2f}%")

    # ============ 可视化结果 ============
    if results and any('error' not in r or not r['error'] for r in results):
        # 在图像上绘制ROI
        result_image = original_image.copy()
        if roi:
            result_image = camera.draw_roi_on_image(result_image, roi)

        # 添加识别结果文本
        if best_result and best_result.get('text'):
            # 创建半透明背景
            overlay = result_image.copy()
            h, w = result_image.shape[:2]

            # 计算文本区域高度
            text_lines = 5
            text_height = 30 * text_lines + 20

            cv2.rectangle(overlay, (0, 0), (w, text_height), (0, 0, 0), -1)
            result_image = cv2.addWeighted(overlay, 0.5, result_image, 0.5, 0)

            # 添加最佳结果文本
            engine_text = f"引擎: {best_result.get('engine', 'Unknown')}"
            cv2.putText(result_image, engine_text, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            confidence_text = f"置信度: {best_result['confidence']:.1f}%"
            cv2.putText(result_image, confidence_text, (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)

            # 显示文本内容（分多行显示）
            text_to_display = best_result['text']
            max_chars_per_line = 40
            y_pos = 90

            for i in range(0, len(text_to_display), max_chars_per_line):
                line = text_to_display[i:i + max_chars_per_line]
                cv2.putText(result_image, line, (10, y_pos),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                y_pos += 20

                # 最多显示5行
                if y_pos > text_height - 10:
                    if i + max_chars_per_line < len(text_to_display):
                        cv2.putText(result_image, "...", (10, y_pos),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    break

        # 显示结果图像
        cv2.imshow("OCR识别结果 (按任意键继续)", result_image)
        cv2.waitKey(0)

        # 保存结果
        output_path = "./ocr_result.jpg"
        cv2.imwrite(output_path, result_image)
        print(f"\n✅ 结果图像已保存到: {output_path}")

        # 如果选择了ROI，保存ROI图像
        if roi:
            roi_path = camera.save_roi_image(original_image, roi, save_path="./roi_extracted.jpg")
            print(f"✅ ROI图像已保存: {roi_path}")

        # 保存文本结果到文件
        text_output_path = "./ocr_result.txt"
        with open(text_output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("OCR识别结果\n")
            f.write("=" * 60 + "\n\n")

            for result in results:
                f.write(f"引擎: {result.get('engine', 'Unknown')}\n")
                f.write(f"语言: {result.get('language', 'N/A')}\n")

                if result.get("error"):
                    f.write(f"错误: {result['error']}\n")
                else:
                    f.write(f"文本: {result['text']}\n")
                    f.write(f"置信度: {result['confidence']:.2f}%\n")
                    f.write(f"单词数量: {result['word_count']}\n")

                f.write("\n" + "-" * 40 + "\n\n")

            if roi:
                f.write(f"ROI区域: {roi}\n")

        print(f"✅ 文本结果已保存到: {text_output_path}")

    cv2.destroyAllWindows()
    print("\n✅ 程序执行完成")


if __name__ == "__main__":
    main()