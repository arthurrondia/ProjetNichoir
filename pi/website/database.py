from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()
class ImageEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())