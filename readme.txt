1. Navigate to your project folder
cd /path/to/your/project
2. Create a virtual environment (named venv)
python3 -m venv venv
3. Activate the virtual environment
source venv/bin/activate
4. Upgrade pip (recommended)
pip install --upgrade pip
5. Install dependencies from requirements.txt
pip install -r requirements.txt
6. Run your Python project

Replace main.py with your actual entry file:

python main.py
Optional: Deactivate venv when done
deactivate
One-liner (quick setup)

If you want to do most steps in one go:

python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && python main.py
