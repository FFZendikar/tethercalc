import os
from urllib.parse import urlparse, parse_qs

from flask import Flask, render_template, request, redirect, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from tethercalc import tethercalc, get_last_fight_id, TetherCalcException

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Report(db.Model):
    report_id = db.Column(db.String(16), primary_key=True)
    fight_id = db.Column(db.Integer, primary_key=True)
    results = db.Column(db.JSON)
    friends = db.Column(db.JSON)

def decompose_url(url):
    parts = urlparse(url)

    report_id = [segment for segment in parts.path.split('/') if segment][-1]
    try:
        fight_id = parse_qs(parts.fragment)['fight'][0]
    except KeyError:
        raise TetherCalcException("Fight ID is required. Select a fight first")

    if fight_id == 'last':
        fight_id = get_last_fight_id(report_id)

    fight_id = int(fight_id)

    return report_id, fight_id


@app.route('/', methods=['GET', 'POST'])
def homepage():
    """Simple form for redirecting to a report, no validation"""
    if request.method == 'POST':
        report_url = request.form['report_url']
        try:
            report_id, fight_id = decompose_url(report_url)
        except TetherCalcException as exception:
            return render_template('error.html', exception=exception)

        return redirect(url_for('calc', report_id=report_id, fight_id=fight_id))

    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html', report_count=Report.query.count())

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/png')

@app.route('/<string:report_id>/<int:fight_id>')
def calc(report_id, fight_id):
    """The actual calculated results view"""
    # Very light validation, more for the db query than for the user
    if len(report_id) != 16:
        return redirect(url_for('homepage'))

    report = Report.query.filter_by(report_id=report_id, fight_id=fight_id).first()

    if report:
        results = report.results
        # These get returned with string keys, so have to massage it some
        friends = {int(k):v for k,v in report.friends.items()}
    else:
        try:
            results, friends = tethercalc(report_id, fight_id)
        except TetherCalcException as exception:
            return render_template('error.html', exception=exception)
        report = Report(
            report_id=report_id,
            fight_id=fight_id,
            results=results,
            friends=friends)
        try:
            db.session.add(report)
            db.session.commit()
        except IntegrityError as exception:
            # This was likely added while tethercalc was running,
            # in which case we don't need to do anything besides redirect
            pass

    return render_template('calc.html', results=results, friends=friends)
