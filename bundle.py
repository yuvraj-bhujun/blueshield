import os

# Define the file extensions you want to include
VALID_EXTENSIONS = ('.py', '.html', '.js', '.css', '.json', 'requirements.txt', '.md')

# Define directories to ignore to keep the output clean
IGNORE_DIRS = {'venv', '.venv', '__pycache__', '.git', 'node_modules', 'static/images'}

output_filename = "combined_project.txt"

with open(output_filename, "w", encoding="utf-8") as outfile:
    for root, dirs, files in os.walk("."):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        for file in files:
            if file.endswith(VALID_EXTENSIONS) and file != "bundle.py":
                file_path = os.path.join(root, file)
                outfile.write(f"\n\n=========================================\n")
                outfile.write(f"FILE: {file_path}\n")
                outfile.write(f"=========================================\n\n")
                
                try:
                    with open(file_path, "r", encoding="utf-8") as infile:
                        outfile.write(infile.read())
                except Exception as e:
                    outfile.write(f"[Error reading file: {e}]\n")

print(f"Done! Your project code is combined in '{output_filename}'.")