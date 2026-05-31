# dump_code.py 라는 이름으로 프로젝트 루트에 저장 후 실행해보세요.
import os

target_extensions = ['.py'] # 검검받고 싶은 확장자
exclude_dirs = ['.git', '__pycache__', 'venv', '.venv', 'build', 'dist']

with open('project_dump4.txt', 'w', encoding='utf-8') as outfile:
    for root, dirs, files in os.walk('.'):
        # 제외할 디렉토리 필터링
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            if any(file.endswith(ext) for ext in target_extensions):
                file_path = os.path.join(root, file)
                if file == 'dump_code.py' or file == 'project_dump.txt':
                    continue
                
                outfile.write(f"\n\n{'='*40}\n")
                outfile.write(f"📄 FILE: {file_path}\n")
                outfile.write(f"{'='*40}\n\n")
                
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as infile:
                    outfile.write(infile.read())

print("✅ project_dump.txt 파일이 생성되었습니다! 이 파일 내용을 복사해서 대화창에 올려주세요.")