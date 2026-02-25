import dash
from dash import html

app = dash.Dash(__name__, title="Amazon Rainforest Dashboard")
server = app.server

app.layout = html.Div("Loading...")

if __name__ == "__main__":
    app.run(debug=True, port=8050)
