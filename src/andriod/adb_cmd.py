import subprocess

class ADBWrapper:
    # def __init__(self,test_log_handle, device_id=None):
    #     self.test_log = test_log_handle
    #     self.device_id = device_id

    def __init__(self, device_id=None):
        self.device_id = device_id

    def run_adb_command(self, command):
        if self.device_id:
            if isinstance(command, str):
                command = f"adb -s {self.device_id} {command}"
            else:
                command = ["adb", "-s", self.device_id] + command
        else:
            if isinstance(command, str):
                command = f"adb {command}"
            else:
                command = ["adb"] + command
        # self.test_log.log_info("[adb cmd]: {}".format(command))
        result = subprocess.run(command, shell=isinstance(command, str), capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ADB command execute fail: {result.stderr}")
        return result.stdout.strip()

    def get_devices(self):
        output = self.run_adb_command("devices")
        devices = []
        for line in output.splitlines()[1:]:  # 跳过第一行标题
            if line.strip():
                devices.append(line.split()[0])
        if self.device_id == None:
            self.device_id = devices[0]
        return devices
    def install_apk(self, apk_path):
        self.run_adb_command(f"install {apk_path}")

    def uninstall_app(self, package_name):
        self.run_adb_command(f"uninstall {package_name}")
    def pull_file(self, remote_path, local_path):
        self.run_adb_command(f"pull {remote_path} {local_path}")

    def push_file(self, local_path, remote_path):
        self.run_adb_command(f"push {local_path} {remote_path}")

    def shell_command(self, shell_cmd):
        return self.run_adb_command(f"shell {shell_cmd}")

    def reboot(self):
        """重启设备。"""
        self.run_adb_command("reboot")

    def get_logcat(self):
        return self.run_adb_command("logcat -d")

    def clear_logcat(self):
        self.run_adb_command("logcat -c")

if __name__ == "__main__":
    adb = ADBWrapper()
    devices = adb.get_devices()
    print("devices:", devices)
    if devices:
        adb = ADBWrapper(devices[0])
        output = adb.shell_command("ls /sdcard")
        print("sdcard show:", output)