import os
import easyocr
import cv2
import numpy as np
import pytesseract
from PIL import Image
import warnings
import datetime
from src.test_log.logger import TestLog

warnings.filterwarnings('ignore')
pytesseract.pytesseract.tesseract_cmd = r'D:\software\tesseract-ocr\tesseract.exe'


class CameraUtils:
    """
    摄像头工具类
    功能：截图、黑屏检测、白屏检测、文字识别、物体识别、ROI选择
    """

    def __init__(self, tesseract_path=None):
        """
        初始化CameraUtils类

        参数：
            tesseract_path: Tesseract OCR可执行文件路径（可选）
        """
        self.cap = None
        self.is_camera_opened = False

        # 设置Tesseract路径（如果需要）
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

        # 预加载物体检测的Haar级联分类器
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        self.eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_eye.xml'
        )

        # 物体检测的颜色范围（示例：红色物体）
        self.color_ranges = {
            'red': [(0, 100, 100), (10, 255, 255)],
            'blue': [(100, 100, 100), (130, 255, 255)],
            'green': [(40, 100, 100), (80, 255, 255)]
        }
        # now = datetime.datetime.now()
        # str_now = now.strftime('%Y_%m_%d_%H_%M_%S')
        # log_folder_name = "camera_" + str_now + ".log"
        # test_log_file = os.path.join(os.getcwd(), log_folder_name)
        # self.test_log = TestLog(test_log_file)

        # 设置Tessdata路径（重要！确保中文语言包能被找到）
        tessdata_dir = r"D:\software\tesseract-ocr\tessdata"
        if os.path.exists(tessdata_dir):
            os.environ['TESSDATA_PREFIX'] = tessdata_dir
            print(f"✅ Tessdata路径: {tessdata_dir}")

    # ============ 新增的 ROI 相关方法 ============
    # 在 CameraUtils 类中新增以下方法

    def recognize_chinese_easyocr(self, frame, gpu=False):
        """
        使用 EasyOCR 识别简体中文文本

        参数：
            frame: 图像帧 (numpy数组)
            gpu: 是否启用GPU加速 (默认为False)

        返回：
            dict: 包含识别结果的字典，格式与原有方法保持一致
        """
        if frame is None:
            return {"text": "", "confidence": 0, "error": "无效帧"}

        try:
            import easyocr

            # 初始化简体中文Reader[citation:4][citation:7]
            reader = easyocr.Reader(['ch_sim'], gpu=gpu)

            # 进行识别，frame 可以是 OpenCV 的 numpy 数组[citation:10]
            result = reader.readtext(frame, detail=1)

            if not result:
                return {"text": "", "confidence": 0, "words_info": []}

            # 提取文本并计算平均置信度
            texts = []
            confidences = []
            words_info = []

            for (bbox, text, prob) in result:
                texts.append(text)
                confidences.append(prob)
                # 构建单词信息（与Tesseract输出结构类似）
                words_info.append({
                    'text': text,
                    'confidence': prob,
                    'position': bbox  # EasyOCR返回的是多边形四点坐标
                })

            full_text = ''.join(texts)  # 中文通常直接拼接
            avg_confidence = float(np.mean(confidences)) if confidences else 0

            return {
                "text": full_text,
                "confidence": avg_confidence,
                "word_count": len(texts),
                "words_info": words_info,
                "recognizer": "easyocr_ch"
            }

        except Exception as e:
            return {"text": "", "confidence": 0, "error": f"EasyOCR识别失败: {str(e)}"}

    def recognize_text_easyocr(self, frame, lang_list=['ch_sim', 'en'], gpu=False):
        """
        使用 EasyOCR 识别混合语言文本（默认中英文）

        参数：
            frame: 图像帧
            lang_list: 语言列表，默认为['ch_sim', 'en'][citation:1][citation:7]
            gpu: 是否启用GPU加速

        返回：
            dict: 包含识别结果的字典
        """
        if frame is None:
            return {"text": "", "confidence": 0, "error": "无效帧"}

        try:
            import easyocr

            # 初始化多语言Reader[citation:1][citation:3]
            reader = easyocr.Reader(lang_list, gpu=gpu)

            # 进行识别
            result = reader.readtext(frame, detail=1)

            if not result:
                return {"text": "", "confidence": 0, "words_info": []}

            # 提取文本并计算平均置信度
            texts = []
            confidences = []
            words_info = []

            for (bbox, text, prob) in result:
                texts.append(text)
                confidences.append(prob)
                words_info.append({
                    'text': text,
                    'confidence': prob,
                    'position': bbox
                })

            full_text = ' '.join(texts)  # 混合语言用空格连接更合适
            avg_confidence = float(np.mean(confidences)) if confidences else 0

            return {
                "text": full_text,
                "confidence": avg_confidence,
                "word_count": len(texts),
                "words_info": words_info,
                "recognizer": f"easyocr_{'_'.join(lang_list)}"
            }

        except Exception as e:
            return {"text": "", "confidence": 0, "error": f"EasyOCR识别失败: {str(e)}"}
    def select_roi_interactive(self, image, window_name="选择识别区域"):
        """
        交互式选择感兴趣区域(ROI)

        参数:
            image: 输入图像
            window_name: 窗口名称

        返回:
            tuple: (x, y, w, h) 或 None（如果取消）
        """
        print("\n" + "=" * 60)
        print("ROI 选择说明:")
        print("1. 用鼠标拖拽绘制矩形框")
        print("2. 按 Enter 确认选择")
        print("3. 按 ESC 取消选择（使用全图）")
        print("4. 按 Space 重新选择")
        print("=" * 60)

        # 显示图像并选择ROI
        roi = cv2.selectROI(window_name, image, showCrosshair=True, fromCenter=False)
        cv2.destroyWindow(window_name)

        # 检查是否选择了有效区域（按ESC会返回(0,0,0,0)）
        if roi == (0, 0, 0, 0):
            print("⚠️ 未选择区域，将使用全图识别")
            return None

        x, y, w, h = roi
        print(f"✅ 已选择区域: x={x}, y={y}, 宽度={w}, 高度={h}")
        return roi

    def extract_roi(self, image, roi):
        """
        从图像中提取ROI区域

        参数:
            image: 原始图像
            roi: (x, y, w, h) 或 None

        返回:
            numpy.ndarray: ROI图像
        """
        if roi is None:
            return image

        x, y, w, h = roi

        # 确保ROI在图像范围内
        height, width = image.shape[:2]
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = min(w, width - x)
        h = min(h, height - y)

        if w <= 0 or h <= 0:
            print("⚠️ ROI区域无效，使用全图")
            return image

        return image[y:y + h, x:x + w]

    def recognize_chinese_text_in_roi(self, image, roi=None, lang='chi_sim', preprocess=True):
        """
        在指定ROI区域内识别中文文本

        参数:
            image: 原始图像
            roi: (x, y, w, h) 或 None（使用全图）
            lang: 语言代码
            preprocess: 是否预处理

        返回:
            dict: 识别结果，包含ROI信息
        """
        # 提取ROI区域
        roi_image = self.extract_roi(image, roi)

        # 识别文本
        result = self.recognize_chinese_text(roi_image, lang, preprocess)

        # 添加ROI信息
        result['roi'] = roi
        result['roi_image_shape'] = roi_image.shape if roi_image is not None else None

        # 如果有ROI，显示提取的区域
        if roi is not None and roi_image is not None:
            cv2.imshow("提取的ROI区域", roi_image)
            cv2.waitKey(500)
            cv2.destroyWindow("提取的ROI区域")

            # 显示预处理后的图像
            if preprocess:
                gray = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)
                if 'chi' in lang:
                    gray = cv2.medianBlur(gray, 3)
                    _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                else:
                    processed = cv2.adaptiveThreshold(
                        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                        cv2.THRESH_BINARY, 11, 2
                    )
                cv2.imshow("预处理后的ROI", processed)
                cv2.waitKey(500)
                cv2.destroyWindow("预处理后的ROI")

        return result

    def draw_roi_on_image(self, image, roi, color=(0, 0, 255), thickness=2):
        """
        在图像上绘制ROI矩形框

        参数:
            image: 原始图像
            roi: (x, y, w, h)
            color: 边框颜色 (B, G, R)
            thickness: 边框厚度

        返回:
            numpy.ndarray: 绘制了ROI的图像
        """
        if roi is None:
            return image

        result = image.copy()
        x, y, w, h = roi

        # 绘制矩形框
        cv2.rectangle(result, (x, y), (x + w, y + h), color, thickness)

        # 添加角标
        corner_size = 15
        # 左上角
        cv2.line(result, (x, y), (x + corner_size, y), color, thickness)
        cv2.line(result, (x, y), (x, y + corner_size), color, thickness)
        # 右上角
        cv2.line(result, (x + w, y), (x + w - corner_size, y), color, thickness)
        cv2.line(result, (x + w, y), (x + w, y + corner_size), color, thickness)
        # 左下角
        cv2.line(result, (x, y + h), (x + corner_size, y + h), color, thickness)
        cv2.line(result, (x, y + h), (x, y + h - corner_size), color, thickness)
        # 右下角
        cv2.line(result, (x + w, y + h), (x + w - corner_size, y + h), color, thickness)
        cv2.line(result, (x + w, y + h), (x + w, y + h - corner_size), color, thickness)

        # 添加ROI信息标签
        label = f"ROI: [{x},{y},{w},{h}]"
        cv2.putText(result, label, (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        return result

    def save_roi_image(self, image, roi, save_path=None):
        """
        保存ROI区域图像

        参数:
            image: 原始图像
            roi: (x, y, w, h)
            save_path: 保存路径

        返回:
            str: 保存的路径
        """
        if roi is None:
            return None

        roi_image = self.extract_roi(image, roi)

        if save_path is None:
            # 自动生成文件名
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = f"roi_{timestamp}.jpg"

        cv2.imwrite(save_path, roi_image)
        print(f"✅ ROI图像已保存: {save_path}")
        return save_path

    # ============ 修改现有的 recognize_chinese_text 方法 ============

    def recognize_chinese_text(self, frame, lang='chi_sim', preprocess=True):
        """
        识别图像中的中文文本（改进版）

        参数：
            frame: 图像帧
            lang: 语言代码，如'chi_sim', 'chi_tra'等
            preprocess: 是否进行预处理

        返回：
            dict: 包含识别结果的字典
        """
        if frame is None:
            return {"text": "", "confidence": 0, "error": "无效帧"}

        try:
            # 检查中文语言包配置
            if 'chi' in lang:
                # 设置中文识别的Tessdata路径
                tessdata_dir = r"D:\software\tesseract-ocr\tessdata"
                if os.path.exists(tessdata_dir):
                    os.environ['TESSDATA_PREFIX'] = tessdata_dir

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if preprocess:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                # 中文文本预处理
                if 'chi' in lang:
                    # 1. 降噪
                    gray = cv2.medianBlur(gray, 3)

                    # 2. 增强对比度
                    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                    gray = clahe.apply(gray)

                    # 3. 二值化
                    _, processed = cv2.threshold(gray, 0, 255,
                                                 cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                else:
                    # 英文预处理
                    processed = cv2.adaptiveThreshold(
                        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                        cv2.THRESH_BINARY, 11, 2
                    )

                rgb_frame = cv2.cvtColor(processed, cv2.COLOR_GRAY2RGB)

            pil_image = Image.fromarray(rgb_frame)

            # 中文识别配置
            custom_config = ''
            if 'chi' in lang:
                # 中文配置：使用LSTM，设置Tessdata路径
                custom_config = f'--tessdata-dir "D:/software/tesseract-ocr/tessdata" --oem 3 --psm 6'
            else:
                custom_config = r'--oem 3 --psm 3'

            # 获取OCR数据
            data = pytesseract.image_to_data(
                pil_image,
                lang=lang,
                config=custom_config,
                output_type=pytesseract.Output.DICT
            )

            # 提取文本（中文不分割空格）
            if 'chi' in lang:
                text = ''.join([word for word in data['text'] if word.strip()])
            else:
                text = ' '.join([word for word in data['text'] if word.strip()])

            # 计算置信度
            confidences = [conf for conf in data['conf'] if conf != -1]
            avg_confidence = np.mean(confidences) if confidences else 0

            # 提取单词位置信息
            words_info = []
            n_boxes = len(data['level'])
            for i in range(n_boxes):
                if int(data['conf'][i]) > 0:  # 只保留置信度大于0的
                    words_info.append({
                        'text': data['text'][i],
                        'confidence': int(data['conf'][i]),
                        'position': (
                            int(data['left'][i]),
                            int(data['top'][i]),
                            int(data['width'][i]),
                            int(data['height'][i])
                        )
                    })

            return {
                "text": text,
                "confidence": float(avg_confidence),
                "word_count": len([w for w in data['text'] if w.strip()]),
                "words_info": words_info,
                "detailed_data": data
            }

        except Exception as e:
            error_msg = str(e)
            if "chi_sim" in error_msg and "tessdata" in error_msg:
                error_msg += "\n请确保：\n1. 中文语言包已安装到 D:\\software\\tesseract-ocr\\tessdata\\\n2. 文件名为 chi_sim.traineddata"
            return {"text": "", "confidence": 0, "error": error_msg}

    # ============ 以下是你原有的方法，保持不变 ============

    def open_camera(self, camera_index=0):
        """
        打开摄像头
        （原有代码保持不变）
        """
        self.cap = cv2.VideoCapture(camera_index)
        self.is_camera_opened = self.cap.isOpened()
        return self.is_camera_opened

    def release_camera(self):
        """释放摄像头资源"""
        if self.cap:
            self.cap.release()
            self.is_camera_opened = False

    def capture_frame(self):
        """
        捕获当前帧
        （原有代码保持不变）
        """
        if not self.is_camera_opened:
            print("摄像头未打开！")
            return None

        ret, frame = self.cap.read()
        if ret:
            return frame
        else:
            print("无法捕获帧")
            return None

    def screenshot(self, save_path=None, show_preview=False):
        """
        截图并保存
        （原有代码保持不变）
        """
        frame = self.capture_frame()

        if frame is None:
            return None

        if save_path:
            cv2.imwrite(save_path, frame)
            print(f"截图已保存到: {save_path}")

        if show_preview:
            cv2.imshow('Screenshot Preview', frame)
            cv2.waitKey(1000)  # 显示1秒
            cv2.destroyWindow('Screenshot Preview')

        return frame

    def read_image(self, image_path):
        """
        读取图像
        （原有代码保持不变）
        """
        image = cv2.imread(image_path)
        return image

    def is_black_screen(self, frame, threshold=10):
        """
        检测是否为黑屏
        （原有代码保持不变）
        """
        if frame is None:
            return True, 0

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        avg_brightness = np.mean(gray)
        is_black = avg_brightness < threshold
        return is_black, avg_brightness

    def is_white_screen(self, frame, threshold=240):
        """
        检测是否为白屏
        （原有代码保持不变）
        """
        if frame is None:
            return False, 0

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        avg_brightness = np.mean(gray)
        is_white = avg_brightness > threshold
        return is_white, avg_brightness

    def detect_screen_condition(self, frame, black_threshold=10, white_threshold=240):
        """
        综合检测屏幕状态
        （原有代码保持不变）
        """
        if frame is None:
            return {"status": "error", "message": "无效帧"}

        black_result, black_value = self.is_black_screen(frame, black_threshold)
        white_result, white_value = self.is_white_screen(frame, white_threshold)

        status = "normal"
        if black_result:
            status = "black_screen"
        elif white_result:
            status = "white_screen"

        return {
            "status": status,
            "black_screen": black_result,
            "white_screen": white_result,
            "brightness": float(black_value),
            "thresholds": {
                "black": black_threshold,
                "white": white_threshold
            }
        }

    def recognize_text(self, frame, lang='eng', preprocess=True):
        """
        识别图像中的文字（英文）
        （原有代码保持不变）
        """
        if frame is None:
            return {"text": "", "confidence": 0, "error": "无效帧"}

        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if preprocess:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                processed = cv2.adaptiveThreshold(
                    gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY, 11, 2
                )
                rgb_frame = cv2.cvtColor(processed, cv2.COLOR_GRAY2RGB)

            pil_image = Image.fromarray(rgb_frame)
            data = pytesseract.image_to_data(
                pil_image,
                lang=lang,
                output_type=pytesseract.Output.DICT
            )

            text = ' '.join([word for word in data['text'] if word.strip()])
            confidences = [conf for conf in data['conf'] if conf != -1]
            avg_confidence = np.mean(confidences) if confidences else 0

            return {
                "text": text,
                "confidence": float(avg_confidence),
                "word_count": len(data['text']),
                "detailed_data": data
            }

        except Exception as e:
            return {"text": "", "confidence": 0, "error": str(e)}

    def detect_faces(self, frame, scale_factor=1.1, min_neighbors=5):
        """
        检测人脸
        （原有代码保持不变）
        """
        if frame is None:
            return [], frame

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=scale_factor,
            minNeighbors=min_neighbors
        )

        result_frame = frame.copy()
        for (x, y, w, h) in faces:
            cv2.rectangle(result_frame, (x, y), (x + w, y + h), (255, 0, 0), 2)

        return faces.tolist(), result_frame

    def detect_color_objects(self, frame, color='red', min_area=100):
        """
        检测特定颜色的物体
        （原有代码保持不变）
        """
        if frame is None or color not in self.color_ranges:
            return [], frame

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower, upper = self.color_ranges[color]
        lower = np.array(lower)
        upper = np.array(upper)

        mask = cv2.inRange(hsv, lower, upper)
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        objects = []
        result_frame = frame.copy()

        for contour in contours:
            area = cv2.contourArea(contour)
            if area > min_area:
                x, y, w, h = cv2.boundingRect(contour)
                objects.append({
                    'position': (int(x), int(y)),
                    'size': (int(w), int(h)),
                    'area': float(area),
                    'center': (int(x + w / 2), int(y + h / 2))
                })

                cv2.rectangle(result_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(result_frame, f'{color} object', (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        return objects, result_frame

    def detect_contours(self, frame, min_area=500, max_area=50000):
        """
        检测所有轮廓
        （原有代码保持不变）
        """
        if frame is None:
            return [], frame

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        objects = []
        result_frame = frame.copy()

        for contour in contours:
            area = cv2.contourArea(contour)
            if min_area < area < max_area:
                x, y, w, h = cv2.boundingRect(contour)
                objects.append({
                    'position': (int(x), int(y)),
                    'size': (int(w), int(h)),
                    'area': float(area),
                    'center': (int(x + w / 2), int(y + h / 2))
                })

                cv2.drawContours(result_frame, [contour], -1, (0, 0, 255), 2)

        return objects, result_frame

    def real_time_monitoring(self, duration=10, show_detection=False):
        """
        实时监控摄像头
        （原有代码保持不变）
        """
        if not self.is_camera_opened:
            print("请先打开摄像头！")
            return {}

        stats = {
            'total_frames': 0,
            'black_screen_count': 0,
            'white_screen_count': 0,
            'normal_count': 0,
            'text_detected_count': 0,
            'face_detected_count': 0
        }

        print(f"开始实时监控，持续{duration}秒...")
        print("按'q'键可以提前退出")

        start_time = cv2.getTickCount()

        while True:
            current_time = cv2.getTickCount()
            elapsed_time = (current_time - start_time) / cv2.getTickFrequency()

            if elapsed_time > duration:
                break

            frame = self.capture_frame()
            if frame is None:
                continue

            stats['total_frames'] += 1
            screen_status = self.detect_screen_condition(frame)

            if screen_status['status'] == 'black_screen':
                stats['black_screen_count'] += 1
            elif screen_status['status'] == 'white_screen':
                stats['white_screen_count'] += 1
            else:
                stats['normal_count'] += 1

            text_result = self.recognize_text(frame)
            if text_result['text'].strip():
                stats['text_detected_count'] += 1

            if show_detection:
                display_frame = frame.copy()
                cv2.putText(display_frame, f"Status: {screen_status['status']}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(display_frame, f"Brightness: {screen_status['brightness']:.1f}",
                            (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                cv2.imshow('Real-time Monitoring', display_frame)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        if show_detection:
            cv2.destroyAllWindows()

        if stats['total_frames'] > 0:
            for key in ['black_screen_count', 'white_screen_count', 'normal_count',
                        'text_detected_count', 'face_detected_count']:
                stats[f'{key}_percentage'] = (stats[key] / stats['total_frames']) * 100

        return stats

    def process_image_file(self, image_path):
        """
        处理图像文件
        （原有代码保持不变）
        """
        frame = cv2.imread(image_path)

        if frame is None:
            return {"error": "无法读取图像文件"}

        screen_status = self.detect_screen_condition(frame)
        text_result = self.recognize_text(frame)
        faces, face_frame = self.detect_faces(frame)
        contours, contour_frame = self.detect_contours(frame)

        return {
            "image_info": {
                "path": image_path,
                "shape": frame.shape,
                "size": f"{frame.shape[1]}x{frame.shape[0]}"
            },
            "screen_status": screen_status,
            "text_recognition": text_result,
            "face_detection": {
                "face_count": len(faces),
                "faces": faces
            },
            "contour_detection": {
                "contour_count": len(contours),
                "contours": contours
            }
        }


# 使用示例
if __name__ == "__main__":
    # 创建CameraUtils实例
    camera_utils = CameraUtils()

    # 测试ROI功能
    print("测试ROI功能...")

    # 读取测试图像
    test_image_path = "test_image.jpg"  # 替换为你的测试图像
    if os.path.exists(test_image_path):
        image = cv2.imread(test_image_path)

        if image is not None:
            # 1. 显示原始图像
            cv2.imshow("原始图像", image)
            cv2.waitKey(1000)
            cv2.destroyWindow("原始图像")

            # 2. 选择ROI
            roi = camera_utils.select_roi_interactive(image)

            # 3. 识别ROI区域的中文文本
            if roi is not None:
                result = camera_utils.recognize_chinese_text_in_roi(image, roi)
                print(f"ROI识别结果: {result['text']}")
                print(f"置信度: {result['confidence']:.2f}")

                # 4. 显示结果
                result_image = camera_utils.draw_roi_on_image(image, roi)
                cv2.imshow("识别结果", result_image)
                cv2.waitKey(0)
                cv2.destroyAllWindows()
            else:
                print("未选择ROI区域")
    else:
        print(f"测试图像不存在: {test_image_path}")