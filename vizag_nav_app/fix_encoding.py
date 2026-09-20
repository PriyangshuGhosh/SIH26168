import os

path = "c:/Users/anish/Downloads/SIH26168/vizag_nav_app/app/src/main/java/com/vizag/nav/ImuManager.kt"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    content = f.read()

# Strip all non-ASCII characters
content = content.encode("ascii", "ignore").decode("ascii")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
