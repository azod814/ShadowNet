import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a_very_secret_key'
    DATABASE = 'victims.db'
    HOST = '0.0.0.0'
    PORT = 5000
