from flask import Flask
from flask_cors import CORS
from backend.config import Config
from backend.extensions import db, jwt, migrate

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Enable CORS
    CORS(app, supports_credentials=True)

    # Initialize extensions
    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)

    # Register blueprints or routes here
    from backend.auth.routes import auth_bp
    from backend.users.routes import users_bp
    from backend.skills.routes import skills_bp, skill_requests_bp
    from backend.matching.routes import matching_bp, sessions_bp
    from backend.credits.routes import credits_bp
    from backend.payments.routes import payments_bp
    from backend.subscriptions.routes import subscriptions_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(skills_bp, url_prefix='/api/skills')
    app.register_blueprint(skill_requests_bp, url_prefix='/api/skill-requests')
    app.register_blueprint(matching_bp, url_prefix='/api/matches')
    app.register_blueprint(sessions_bp, url_prefix='/api/sessions')
    app.register_blueprint(credits_bp, url_prefix='/api/credits')
    app.register_blueprint(payments_bp, url_prefix='/api/payments')
    app.register_blueprint(subscriptions_bp, url_prefix='/api/subscriptions')

    @app.route('/health')
    def health_check():
        return {'status': 'ok', 'project': 'SkillXchange'}

    return app

if __name__ == '__main__':
    app = create_app()
    app.run()
