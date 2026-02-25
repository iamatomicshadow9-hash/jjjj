import os
import subprocess
import sys

def main():
    # Replit uses port 5000 for webview
    os.environ["PORT"] = "5000"
    
    # If this process was started by the Koyeb launcher, run the bot directly.
    # Otherwise, prefer starting the launcher (`run.py`) if it exists.
    if os.getenv("RUN_BY_KOYEB_LAUNCHER") == "1":
        print("Launched by Koyeb launcher — starting bot directly...")
        subprocess.run([sys.executable, "bot.py"])
        return

    # run.py is the main launcher that handles both the bot and the web server
    if os.path.exists("run.py"):
        print("Starting application via run.py...")
        subprocess.run([sys.executable, "run.py"])
    else:
        print("run.py not found. Falling back to bot.py...")
        subprocess.run([sys.executable, "bot.py"])

    # optionally run krutoy.py if it exists
    if os.path.exists("krutoy.py"):
        try:
            print("Launching krutoy.py...")
            subprocess.run([sys.executable, "krutoy.py"])
        except Exception:
            print("Failed to run krutoy.py")

if __name__ == "__main__":
    main()
