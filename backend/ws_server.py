# -*- coding: utf-8 -*-
import json,logging,os,sys
sys.path.insert(0,os.getcwd())
from fastapi import FastAPI,WebSocket,WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from backend.ai_coach import classify,answer,get_ctx
import uvicorn
app=FastAPI()
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])
