import json
import time
import requests
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objects as go

def get_iss_position():
    url = "http://api.open-notify.org/iss-now.json"
    response = requests.get(url)
    result = response.json()
    location = result["iss_position"]
    lat = float(location["latitude"])
    lon = float(location["longitude"])
    return lat, lon

app = Dash(__name__)

app.layout = html.Div([
    dcc.Graph(id="globe", style={"height": "80vh"}),  
    dcc.Interval(
        id="interval-component",
        interval=500,  
        n_intervals=0
    )
])

@app.callback(
    Output("globe", "figure"),
    [Input("interval-component", "n_intervals")]
)
def update_globe(n):
    lat, lon = get_iss_position()
    #print(f"Latitude: {lat}, Longitude: {lon}")
    fig = go.Figure()
    fig.add_trace(
        go.Scattergeo(
            lon=[lon],
            lat=[lat],
            mode='markers',
            marker=dict(size=10, color="red"),
            name="ISS Position"
        )
    )
    fig.update_layout(
        geo=dict(
            projection_type="orthographic",
            showland=True,
            landcolor="rgb(243, 243, 243)",
            oceancolor="rgb(204, 204, 255)",
            showocean=True,
        ),
        title="ISS Current Location",
        uirevision='constant'  
    )
    return fig

if __name__ == "__main__":
    app.run_server(debug=True)
