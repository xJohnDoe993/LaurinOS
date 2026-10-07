import os, shutil, sys
path = sys.argv[1]
lines = []
if os.path.exists(path):
    with open(path, encoding="utf-8") as handle:
        lines = handle.readlines()
    if not os.path.exists(path + ".before-paimenos"):
        shutil.copy2(path, path + ".before-paimenos")
lines = [line for line in lines if line.split("=", 1)[0].strip() not in {"fullscreen", "native"}]
with open(path, "w", encoding="utf-8") as handle:
    handle.writelines(lines)
    if lines and not lines[-1].endswith("\n"):
        handle.write("\n")
    handle.write("fullscreen=native\nnative=yes\n")
