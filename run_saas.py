import os,sys
sys.path.insert(0,os.getcwd())
from backend.main import app
import uvicorn
port=int(os.environ.get("AURORA_PORT","7878"))
uvicorn.run(app,host="0.0.0.0",port=port)
