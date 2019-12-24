from app import create_app

import os

app = create_app(os.getenv('FLASK_CONFIG') or 'default')


@app.shell_context_processor
def make_shell_context():
    from app import db
    from app.models import User, Task
    return {'db': db, 'User': User, 'Task': Task}


if __name__ == "__main__":
    app.run()
