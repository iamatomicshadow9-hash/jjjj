import os
import subprocess
import sys

def main():
    # Replit uses port 5000 for webview
    os.environ["PORT"] = "5000"
    
    # run.py is the main launcher that handles both the bot and the web server
    if os.path.exists("run.py"):
        print("Starting application via run.py...")
        subprocess.run([sys.executable, "run.py"])
    else:
        print("run.py not found. Falling back to bot.py and web.py...")
        # Fallback logic if run.py is missing (though it was extracted)
        subprocess.run([sys.executable, "bot.py"])

if __name__ == "__main__":
    main()
