import typing
import asyncio
import json
import itertools as it

import aiohttp
import numpy as np

import toga
import toga.widgets.canvas
from toga.colors import rgb, rgba
from toga import colors
from toga.style import Pack


async def get_iss_position():
    url = "http://api.open-notify.org/iss-now.json"

    async with aiohttp.ClientSession() as session:
        response = await session.get(url)
        result = await response.json()
        location = result["iss_position"]
        lon = float(location["longitude"])
        lat = float(location["latitude"])
        return lon, lat


def cylindricalToCartesian(r: float, long: float, lat: float) -> tuple[float, float, float]:
    c = np.cos(lat)

    x = r * c * np.cos(long)
    y = r * c * np.sin(long)
    z = r * np.sin(lat)

    return x, y, z


class StartApp(toga.App):
    polygons: list[list[tuple[float, float, float]]]
    SIZE = 800
    WIDTH = SIZE
    HEIGHT = SIZE
    R = SIZE // 3
    D = int(SIZE / 2.5)

    def loadPolygon(self, poly: list[tuple[float, float]]):
        if len(poly) < 125:
            return

        self.polygons.append([
            cylindricalToCartesian(self.R, long * np.pi / 180, lat * np.pi / 180)
            for long, lat in poly[::max(len(poly)//200, 3)]
        ])

    def loadGeoJson(self, shape: typing.Any):
        match shape['type']:
            case 'Feature':
                self.loadGeoJson(shape['geometry'])
            case 'Polygon':
                self.loadPolygon(shape['coordinates'][0])
            case 'MultiPolygon':
                for poly in shape['coordinates']:
                    self.loadPolygon(poly[0])
            case t:
                print('Invalid type', t)

    def startup(self):
        self.rotation = 0
        self.start_press = None
        self.iss_pos = None

        original = 'World_Continents.geojson'
        self.polygons = []
        with open(original) as f:
            borders = json.load(f)['features']
            for border in borders:
                self.loadGeoJson(border)

        self.canvas = toga.Canvas(
            style=Pack(flex=1),
            on_drag=self.on_drag,
            on_press=self.on_press,
            on_release=self.on_release,
        )

        self.main_window = toga.MainWindow(size=(150, 250))
        self.main_window.content = toga.Box(children=[self.canvas])
        self.main_window.show()

        self.draw()
        asyncio.create_task(self.dataLoop())

    async def dataLoop(self):
        while True:
            self.iss_pos = await get_iss_position()
            self.draw()
            await asyncio.sleep(2.5)

    def drawPolygon(self, points: list[tuple[float, float, float]], color=rgba(255, 200, 150, .75)):
        def nmod(ang, m): return (ang + m) % (2*m) - m

        def getAngleAtBorder(start_long, start_lat, end_long, end_lat):
            if end_lat == start_lat:
                return nmod(start_long + end_long, np.pi) / 2

            ratio = -start_lat / ((end_lat - start_lat) % np.pi)
            return nmod(start_long + nmod(end_long - start_long, np.pi) * ratio, np.pi)

        def cartesianToLongLat(x: float, y: float, z: float) -> tuple[float, float]:
            """

                +z/N
                  |
                  o-- +y/E
                 /
                +x
            """

            # Starts at east side, goes counter clockwise (E-N-W-S)
            long = np.arctan2(z, y)
            # Goes from -x to +x
            lat = np.arctan2(x, (y**2 + z**2)**.5)

            return long, lat

        # with self.canvas.Fill(color=rgb(*[min(len(points), 255)]*3)) as fill:
        with self.canvas.Fill(color=color) as fill:
            def add(shape): return fill.drawing_objects.append(shape)
            start_pos: tuple[float, float, float] | None = None
            last_inside_pos: tuple[float, float, float] | None = None
            last_outside_pos: tuple[float, float, float] | None = None

            for x, y, z in it.chain(points, [points[0]]):
                if x < 0:
                    if last_outside_pos is None and last_inside_pos is not None:
                        crossing_angle = getAngleAtBorder(*cartesianToLongLat(x, y, z), *cartesianToLongLat(*last_inside_pos))
                        add(toga.widgets.canvas.LineTo(self.WIDTH/2 + self.R * np.cos(crossing_angle), self.HEIGHT/2 - self.R * np.sin(crossing_angle)))

                    last_outside_pos = x, y, z
                    continue

                transformed = (y + self.WIDTH/2, -z + self.HEIGHT/2)
                if last_outside_pos is not None:
                    crossing_angle = getAngleAtBorder(*cartesianToLongLat(x, y, z), *cartesianToLongLat(*last_outside_pos))
                    if last_inside_pos is None:
                        add(toga.widgets.canvas.MoveTo(self.WIDTH/2 + self.R * np.cos(crossing_angle), self.HEIGHT/2 - self.R * np.sin(crossing_angle)))
                    else:
                        last_inside_long, _ = cartesianToLongLat(*last_inside_pos)
                        start = -last_inside_long
                        end = -crossing_angle
                        diff = nmod(end - start, np.pi)
                        add(toga.widgets.canvas.Arc(self.WIDTH / 2, self.HEIGHT / 2, self.R, start, end, diff < 0))

                add(toga.widgets.canvas.LineTo(*transformed))
                if start_pos is None:
                    start_pos = (x, y, z)

                last_inside_pos = (x, y, z)
                last_outside_pos = None

            if start_pos and last_outside_pos and last_inside_pos:
                crossing_angle = getAngleAtBorder(*cartesianToLongLat(*start_pos), *cartesianToLongLat(*last_outside_pos))
                last_inside_long, _ = cartesianToLongLat(*last_inside_pos)
                start = -last_inside_long
                end = -crossing_angle
                diff = nmod(end - start, np.pi)
                add(toga.widgets.canvas.Arc(self.WIDTH / 2, self.HEIGHT / 2, self.R, start, end, diff < 0))

            fill.redraw()

    def drawPolygonCylndrical(self, poly: list[tuple[float, float]], color):
        self.drawPolygon([
            cylindricalToCartesian(self.R, long * np.pi / 180 + self.rotation, lat * np.pi / 180)
            for long, lat in poly
        ], color)

    def drawGlobe(self):
        with self.canvas.Fill(color=rgba(50, 60, 80, .5)) as fill:
            fill.ellipse(self.WIDTH / 2, self.HEIGHT / 2, self.R, self.R)
        for poly in self.polygons:
            self.drawPolygon(poly)

    def drawShadow(self):
        if not self.iss_pos: return

        r = .5**.5
        poly = [
            (1, 0),
            (r, r),
            (0, 1),
            (-r, r),
            (-1, 0),
            (-r, -r),
            (0, -1),
            (r, -r)
        ]

        iss_long, iss_lat = self.iss_pos
        self.drawPolygonCylndrical([
            (long + iss_long, lat + iss_lat)
            for long, lat in poly
        ], colors.BLACK)

    def draw(self):
        self.canvas.context.clear()

        if self.iss_pos:
            long, lat = self.iss_pos
            x, y, z, = cylindricalToCartesian(self.D, long * np.pi / 180 + self.rotation, lat * np.pi / 180)
            if x > 0:
                self.drawGlobe()
                self.drawShadow()

            transformed = (y + self.WIDTH/2, -z + self.HEIGHT/2)
            with self.canvas.Fill(color=colors.RED) as fill:
                fill.ellipse(*transformed, 5, 5)

            if x <= 0:
                self.drawGlobe()
        else:
            self.drawGlobe()

    def rotate(self, dx: int):
        angle = -dx * 0.01
        self.rotation += angle

        c = np.cos(angle)
        s = np.sin(angle)
        for poly in self.polygons:
            for i, (x, y, z) in enumerate(poly):
                poly[i] = x*c-y*s, x*s+y*c, z

        self.draw()

    def on_press(self, widget: toga.Canvas, x: int, y: int, **_):
        self.start_press = (x, y)

    def on_release(self, widget: toga.Canvas, x: int, y: int, **_):
        if self.start_press is not None:
            self.rotate(self.start_press[0] - x)

        self.start_press = None

    def on_drag(self, widget: toga.Canvas, dx: int, dy: int, **_):
        self.rotate(dx)

        self.start_press = None


def main():
    return StartApp("Tutorial 4", "org.beeware.toga.tutorial")


if __name__ == "__main__":
    main().main_loop()
