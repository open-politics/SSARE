import os

def copy_additional_files(root_path, output_file):
    files_to_copy = ['main.py', 'celery_worker.py', 'models.py', 'Dockerfile', 'docker-compose.yml', 'config.ini', 'README.md']
    with open(output_file, 'w') as output:
        for root, dirs, files in os.walk(root_path):
            for file in files:
                if file in files_to_copy:
                    file_path = os.path.join(root, file)
                    output.write(f"{file_path}:\n")
                    with open(file_path, 'r') as f:
                        output.write(f.read())
                    output.write("\n\n")

# Usage
root_directory = '.' # Replace with your root directory path
output_filename = 'all.txt' # Replace with your desired output file name
copy_additional_files(root_directory, output_filename)

## Use to copy all files in a directory to a single file
