import sys, json, os
from PyQt6.QtWidgets import *
from PyQt6.QtGui import QPainter, QColor, QPen, QIcon, QPixmap, QTransform
from PyQt6.QtCore import Qt, QSize

M = r"module1\media"
LOGO = f"{M}\\TLgreen.png"
IMG1, IMG2, IMG3, IMG4, IMG5 = f"{M}\\Cbottom.png", f"{M}\\Pedestrain.png", f"{M}\\Block.png", f"{M}\\Zhorizontal.png", f"{M}\\TLyellow.png"
RD1, RD2 = f"{M}\\Rvertical.png", f"{M}\\Rcrossroads.png"
PLACE_IMGS = [IMG1, IMG2, IMG3, IMG4, IMG5]
ROAD_IMGS = [RD1, RD2]
FREE = {IMG2, IMG3}
ROT = {IMG1, IMG2, IMG4, IMG5, RD1, RD2}
CYCLES = {
    IMG1: [IMG1, f"{M}\\BCvertical.png", f"{M}\\GCicon.ico"],
    IMG3: [IMG3, f"{M}\\Stop.png", f"{M}\\Start.png"],
    IMG5: [IMG5, f"{M}\\TLred.png", f"{M}\\TLgreen.png"],
}
CELL, COLS, ROWS = 36, 21, 21


def px(path, rot=0):
    p = QPixmap(path)
    return p.transformed(QTransform().rotate(rot)) if rot and not p.isNull() else p


class Grid(QWidget):
    def __init__(self, side):
        super().__init__()
        self.setFixedSize(COLS * CELL, ROWS * CELL)
        self.side = side
        self.roads, self.objs = {}, {}
        self.mode = self.sel = None

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(235, 235, 235))
        for layer in (self.roads, self.objs):
            for (x, y), o in layer.items():
                img = px(o["path"], o["rot"])
                if not img.isNull():
                    p.drawPixmap(x * CELL, y * CELL, CELL, CELL, img)
        p.setPen(QPen(QColor(0, 0, 0, 50)))
        for c in range(COLS + 1):
            p.drawLine(c * CELL, 0, c * CELL, ROWS * CELL)
        for r in range(ROWS + 1):
            p.drawLine(0, r * CELL, COLS * CELL, r * CELL)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        x, y = int(e.position().x() // CELL), int(e.position().y() // CELL)
        if not (0 <= x < COLS and 0 <= y < ROWS):
            return
        c = (x, y)
        if self.mode == 'road' and self.sel:
            self.roads[c] = {"path": self.sel, "base": self.sel, "rot": 0}
        elif self.mode == 'place' and self.sel:
            if c in self.roads or self.sel in FREE:
                self.objs[c] = {"path": self.sel, "base": self.sel, "rot": 0, "speed": 0}
        elif self.mode == 'place':
            o = self.objs.get(c) or self.roads.get(c)
            if o:
                self.side.show_props(c, o, self)
        self.update()

    def save(self, path):
        data = {"roads": {f"{k[0]},{k[1]}": v for k, v in self.roads.items()},
                "objs": {f"{k[0]},{k[1]}": v for k, v in self.objs.items()}}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        parse = lambda d: {tuple(map(int, k.split(","))): v for k, v in d.items()}
        self.roads = parse(data.get("roads", {}))
        self.objs = parse(data.get("objs", {}))
        self.update()


class Side(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(120)
        self.grid = None
        self.ibtns = []
        self.vb = QVBoxLayout(self)
        self.sp = self._sec(PLACE_IMGS)
        self.sr = self._sec(ROAD_IMGS)
        self.props = QWidget()
        self.pvb = QVBoxLayout(self.props)
        for w in (self.sp, self.sr, self.props):
            w.hide()
            self.vb.addWidget(w)
        self.vb.addStretch()

    def _sec(self, paths):
        w = QWidget()
        vb = QVBoxLayout(w)
        for p in paths:
            b = QPushButton()
            b.setFixedSize(100, 100)
            b.setCheckable(True)
            b.setProperty("path", p)
            ic = px(p)
            if not ic.isNull():
                b.setIcon(QIcon(ic))
                b.setIconSize(QSize(88, 88))
            else:
                b.setText(os.path.basename(p)[:8])
            b.clicked.connect(self._pick)
            vb.addWidget(b)
            self.ibtns.append(b)
        return w

    def _pick(self):
        s = self.sender()
        for b in self.ibtns:
            if b is not s:
                b.setChecked(False)
        if self.grid:
            self.grid.sel = s.property("path") if s.isChecked() else None

    def switch(self, place=False, road=False):
        for b in self.ibtns:
            b.setChecked(False)
        if self.grid:
            self.grid.sel = None
            self.grid.mode = 'place' if place else ('road' if road else None)
        self.props.hide()
        self.sp.setVisible(place)
        self.sr.setVisible(road)

    def show_props(self, cell, obj, grid):
        while self.pvb.count():
            w = self.pvb.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.props.show()
        base = obj["base"]
        self.pvb.addWidget(QLabel(f"<b>{os.path.basename(base)}</b>"))

        if base in ROT:
            b = QPushButton("Повернуть")
            b.clicked.connect(lambda: (obj.update(rot=(obj["rot"] + 90) % 360), grid.update()))
            self.pvb.addWidget(b)

        if base in CYCLES:
            b = QPushButton("Изменить тип")
            c = CYCLES[base]
            def color():
                i = c.index(obj["path"]) if obj["path"] in c else 0
                obj["path"] = c[(i + 1) % len(c)]
                grid.update()
            b.clicked.connect(color)
            self.pvb.addWidget(b)

        if base == IMG2:
            lbl = QLabel(f"Скорость: {obj.get('speed', 0)} сек")
            self.pvb.addWidget(lbl)
            for txt in ("+5", "-5"):
                b = QPushButton(txt)
                b.clicked.connect(lambda: None)
                self.pvb.addWidget(b)

        b = QPushButton("Удалить")
        def dele():
            grid.objs.pop(cell, None)
            grid.roads.pop(cell, None)
            grid.update()
            self.props.hide()
        b.clicked.connect(dele)
        self.pvb.addWidget(b)


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Интеллектуальная Дорожная Система")
        lp = QPixmap(LOGO)
        if not lp.isNull():
            self.setWindowIcon(QIcon(lp))
        self.side = Side()
        self.grid = Grid(self.side)
        self.side.grid = self.grid

        c = QWidget()
        self.setCentralWidget(c)
        root = QVBoxLayout(c)
        body = QHBoxLayout()
        body.addWidget(self.side)
        body.addWidget(self.grid)
        root.addLayout(body)

        bar = QHBoxLayout()
        self.bp = QPushButton("Добавить объекты")
        self.bp.setCheckable(True)
        self.br = QPushButton("Редактор дороги")
        self.br.setCheckable(True)
        bs = QPushButton("Сохранить")
        bl = QPushButton("Загрузить")
        self.bp.toggled.connect(lambda v: (self.br.setChecked(False), self.side.switch(place=v)))
        self.br.toggled.connect(lambda v: (self.bp.setChecked(False), self.side.switch(road=v)))
        bs.clicked.connect(self._save)
        bl.clicked.connect(self._load)
        for b in (self.bp, self.br, bs, bl):
            bar.addWidget(b)
        root.addLayout(bar)
        self.adjustSize()

    def _save(self):
        fn, _ = QFileDialog.getSaveFileName(self, "", "", "JSON (*.json)")
        if fn:
            self.grid.save(fn)

    def _load(self):
        fn, _ = QFileDialog.getOpenFileName(self, "", "", "JSON (*.json)")
        if fn:
            self.grid.load(fn)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    App().show()
    sys.exit(app.exec())
