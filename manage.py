'''
@Descripttion: 
@version: 
@Author: wangshiwen@36719
@Date: 2019-10-02 20:36:27
@LastEditors  : wangshiwen@36719
@LastEditTime : 2020-01-07 13:01:36
'''
from app import create_app

import os
import dash
import dash_html_components as html

app = create_app(os.getenv('FLASK_CONFIG', 'default'))

dash_app = dash.Dash(
    __name__,
    server=app,
    routes_pathname_prefix='/dash/'
)

dash_app.layout = html.Div("My Dash app")

@app.shell_context_processor
def make_shell_context():
    from app import db
    from app.models import User, Task
    return {'db': db, 'User': User, 'Task': Task}


if __name__ == "__main__":
    app.run()
