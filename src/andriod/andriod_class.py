from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
import time
class AndriodDevice():
    def __init__(self):
        # 使用 AppiumOptions 定义 Desired Capabilities
        self.options = UiAutomator2Options()
        self.options.platform_name = "Android"
        self.options.platform_version = "10"  # 根据 MuMu 模拟器的 Android 版本填写
        self.options.device_name = "127.0.0.1:7555"  # MuMu 模拟器的 ADB 地址
        self.options.app_package = "tv.danmaku.bili"  # 哔哩哔哩的包名
        self.options.app_activity = "tv.danmaku.bili.ui.splash.SplashActivity"  # 哔哩哔哩的主 Activity
        self.options.automation_name = "uiautomator2"  # 自动化引擎
        self.options.no_reset = True  # 不重置应用状态
        self.options.unicode_keyboard = True  # 使用 Unicode 输入法
        self.options.reset_keyboard = True  # 重置输入法
        self.driver = None
    def driver_start(self):
        # 启动 Appium 会话
        # self.driver = webdriver.Remote("http://localhost:4723/wd/hub", self.caps)
        self.driver = webdriver.Remote("http://192.168.3.31:4723/wd/hub",  options = self.options)
    def driver_quit(self):
        if not (self.driver == None):
            self.driver.quit()

class AndriodPad(AndriodDevice):
    pass

class SamsongS9080(AndriodPad):
    def play_blibli(self):
        try:
            # 等待应用启动
            time.sleep(10)
            # 点击首页的第一个视频
            first_video = self.driver.find_element(AppiumBy.XPATH,
                                              "//android.widget.FrameLayout[@resource-id='tv.danmaku.bili:id/recycler_view']/android.view.ViewGroup[1]")
            first_video.click()
            # 等待视频加载
            time.sleep(5)

            # 点击播放按钮
            play_button = self.driver.find_element(AppiumBy.ID, "tv.danmaku.bili:id/play_button")
            play_button.click()

            # 打印日志
            print("video play success")
            # 等待视频播放 10 秒
            time.sleep(10)
        except Exception as e:
            print(e)

if __name__ == '__main__':
    sam  = SamsongS9080()
    sam.driver_start()
    sam.play_blibli()



