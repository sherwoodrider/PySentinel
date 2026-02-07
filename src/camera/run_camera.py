# 导入库
from camera_utils import CameraUtils

# 创建实例
camera = CameraUtils()

# 测试中文识别
# 读取图像
image = camera.read_image("./1.jpg")

# 方法1: 使用EasyOCR识别中文
result_ch = camera.recognize_chinese_easyocr(image, gpu=False) # 根据情况设置gpu
print(f"EasyOCR 中文识别: {result_ch['text']}")
print(f"置信度: {result_ch['confidence']:.2f}")

# 方法2: 使用EasyOCR识别中英文混合
result_mix = camera.recognize_text_easyocr(image, gpu=False)
print(f"EasyOCR 混合识别: {result_mix['text']}")
print(f"置信度: {result_mix['confidence']:.2f}")

# 对比原有的Tesseract方法
result_old = camera.recognize_chinese_text(image)
print(f"Tesseract 识别: {result_old['text']}")
# 打开摄像头
# if camera.open_camera():
#     # 截图
#     # frame = camera.screenshot('./my_screenshot.jpg')
#     #
#     # # 检测黑屏/白屏
#     # is_black, brightness = camera.is_black_screen(frame)
#     # print(f"是否黑屏: {is_black}, 亮度: {brightness}")
#     #
#     # # 文字识别
#     # text_result = camera.recognize_text(frame)
#     # print(f"识别到的文字: {text_result['text']}")
#     #
#     # # # 物体识别
#     # faces, _ = camera.detect_faces(frame)
#     # print(f"检测到 {len(faces)} 张人脸")
#
#     # 实时监控
#     stats = camera.real_time_monitoring(duration=10, show_detection=True)
#
#     # 释放摄像头
#     camera.release_camera()