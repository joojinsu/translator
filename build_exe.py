import os
import sys
import subprocess
import shutil

def build():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(script_dir, "app.py")
    
    print("==================================================")
    print("   Building Modern EasyOCR Translator (.exe)      ")
    print("==================================================")

    # Locate torchvision directory to collect its C-extensions
    import torchvision
    torchvision_dir = os.path.dirname(torchvision.__file__)
    print(f"torchvision directory: {torchvision_dir}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=EasyOCR_Translator",
        "--onedir",
        "--noconsole",
        "--collect-all", "customtkinter",
        "--collect-all", "darkdetect",
        "--collect-all", "easyocr",
        "--collect-all", "pynput",
        "--collect-all", "deep_translator",
        "--collect-all", "pystray",
        "--hidden-import=pystray._win32",
        "--hidden-import=torch",
        "--hidden-import=torchvision",
        "--hidden-import=scipy",
        "--hidden-import=scipy.special",
        "--hidden-import=scipy.ndimage",
        "--hidden-import=pynput.keyboard._win32",
        "--hidden-import=pynput.mouse._win32",
        "--hidden-import=PIL.ImageGrab",
        "--hidden-import=pyperclip",
        "--clean",
        "-y",
        main_script
    ]

    print("Running PyInstaller...")
    result = subprocess.run(cmd, cwd=script_dir)
    
    if result.returncode == 0:
        dist_dir = os.path.join(script_dir, "dist", "EasyOCR_Translator")
        exe_path = os.path.join(dist_dir, "EasyOCR_Translator.exe")
        internal_torchvision = os.path.join(dist_dir, "_internal", "torchvision")

        # CRITICAL FIX for Python 3.14: PyInstaller misses _C_stable.pyd and image_stable.pyd
        print(f"Ensuring torchvision C-extensions in {internal_torchvision}...")
        os.makedirs(internal_torchvision, exist_ok=True)
        for fname in os.listdir(torchvision_dir):
            if fname.endswith(".pyd") or fname.endswith(".dll"):
                src = os.path.join(torchvision_dir, fname)
                dst = os.path.join(internal_torchvision, fname)
                shutil.copy2(src, dst)
                print(f" - Injected torchvision binary: {fname}")

        # Copy downloaded models to dist/EasyOCR_Translator/models for 100% offline standalone usage
        user_model_dir = os.path.join(os.path.expanduser("~"), ".EasyOCR", "model")
        target_model_dir = os.path.join(dist_dir, "models")
        if os.path.exists(user_model_dir):
            print(f"Bundling EasyOCR models to {target_model_dir}...")
            os.makedirs(target_model_dir, exist_ok=True)
            for fname in os.listdir(user_model_dir):
                src_file = os.path.join(user_model_dir, fname)
                dst_file = os.path.join(target_model_dir, fname)
                if os.path.isfile(src_file) and not os.path.exists(dst_file):
                    shutil.copy2(src_file, dst_file)
                    print(f" - Copied model: {fname}")

        print("\n==================================================")
        print(" Build Successful!")
        print(f" Executable: {exe_path}")
        print("==================================================")
    else:
        print("\n[!] Build failed with exit code:", result.returncode)

if __name__ == "__main__":
    build()
