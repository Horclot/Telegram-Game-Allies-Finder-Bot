import subprocess
import time

RESTART_INTERVAL = 180  # 3 минуты

while True:
    print("🚀 Запуск бота...")
    process = subprocess.Popen([
        r"D:\Allies Hub\.venv\Scripts\python.exe", "AlliesHub.py"
    ])

    time.sleep(RESTART_INTERVAL)

    print("🔁 Перезапуск бота...")
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()

    print("⏳ Перезапуск через несколько секунд...\n")
