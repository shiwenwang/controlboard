'''
@Descripttion: 
@version: 
@Author: wangshiwen@36719
@Date: 2019-10-02 20:36:27
@LastEditors: wangshiwen@36719
@LastEditTime: 2019-12-25 10:03:31
'''
from app import create_app

import os

app = create_app(os.getenv('FLASK_CONFIG', 'default'))


@app.shell_context_processor
def make_shell_context():
    from app import db
    from app.models import User, Task
    return {'db': db, 'User': User, 'Task': Task}


if __name__ == "__main__":
    app.run()
