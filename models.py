from extensions import db

class Incident(db.Model):
    id = db.Column(db.String(20), primary_key=True)
    type = db.Column(db.String(100))
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    confidence = db.Column(db.Integer)
    authority = db.Column(db.String(100))
    status = db.Column(db.String(50))
    reported_at = db.Column(db.DateTime)
    description = db.Column(db.Text)

class CoralSample(db.Model):
    id = db.Column(db.String(20), primary_key=True)
    site = db.Column(db.String(100))
    bleaching_pct = db.Column(db.Integer)
    score = db.Column(db.Integer)
    note = db.Column(db.Text)
    submitted = db.Column(db.String(50))