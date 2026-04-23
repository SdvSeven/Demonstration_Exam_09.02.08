import sys, json, os
from PyQt6.QtWidgets import *
from PyQt6.QtGui import QPainter, QColor, QPen, QIcon, QPixmap, QTransform
from PyQt6.QtCore import Qt, QSize

M = r"module1\media"
LOGO = f"{M}\\TLgreen.png"
IMG1, IMG2, IMG3, IMG4, IMG5 = f"{M}\\Cbottom.png", f"{M}\\Pedestrain.png", f"{M}\\Block.png", f"{M}\\Zhorizontal.png", f"{M}\\TLyellow.png"
RD1, RD2 = f"{M}\\Rvertical.png", f"{M}\\Rcrossroads.png"
PLACE_IMGS = [IMG1, IMG2, IMG3, IMG4, IMG5]
ROAD_IMGS  = [RD1, RD2]
FREE   = {IMG2, IMG3}
ROT    = {IMG1, IMG2, IMG4, IMG5, RD1, RD2}
CYCLES = {
    IMG1: [IMG1, f"{M}\\BCvertical.png", f"{M}\\GCicon.ico"],
    IMG3: [IMG3, f"{M}\\Stop.png",       f"{M}\\Start.png"],
    IMG5: [IMG5, f"{M}\\TLred.png",      f"{M}\\TLgreen.png"],
}
CELL, COLS, ROWS = 36, 21, 21

def get_px(path, rot=0):
    p = QPixmap(path)
    return p.transformed(QTransform().rotate(rot)) if rot and not p.isNull() else p

class Grid(QWidget):
    def __init__(self, side):
        super().__init__()
        self.setFixedSize(COLS * CELL, ROWS * CELL)
        self.side = side; self.roads, self.objs = {}, {}; self.mode = self.sel = None

    def paintEvent(self, _):
        p = QPainter(self); p.fillRect(self.rect(), QColor(235, 235, 235))
        for layer in (self.roads, self.objs):
            for (x, y), o in layer.items():
                img = get_px(o["path"], o["rot"])
                if not img.isNull(): p.drawPixmap(x*CELL, y*CELL, CELL, CELL, img)
        p.setPen(QPen(QColor(0, 0, 0, 50)))
        for i in range(COLS+1): p.drawLine(i*CELL, 0, i*CELL, ROWS*CELL)
        for i in range(ROWS+1): p.drawLine(0, i*CELL, COLS*CELL, i*CELL)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton: return
        x, y = int(e.position().x()//CELL), int(e.position().y()//CELL)
        if not (0 <= x < COLS and 0 <= y < ROWS): return
        c = (x, y)
        if self.mode == 'road' and self.sel:
            self.roads[c] = {"path": self.sel, "base": self.sel, "rot": 0}
        elif self.mode == 'place' and self.sel:
            if c in self.roads or self.sel in FREE:
                self.objs[c] = {"path": self.sel, "base": self.sel, "rot": 0, "speed": 0}
        else:
            o = self.objs.get(c) or self.roads.get(c)
            if o: self.side.show_props(c, o, self)
        self.update()

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"roads": {f"{k[0]},{k[1]}": v for k,v in self.roads.items()},
                       "objs":  {f"{k[0]},{k[1]}": v for k,v in self.objs.items()}}, f, indent=2)

    def load(self, path):
        try:
            with open(path, encoding="utf-8") as f: data = json.load(f)
            p = lambda d: {tuple(map(int, k.split(","))): v for k,v in d.items()}
            self.roads, self.objs = p(data.get("roads",{})), p(data.get("objs",{})); self.update()
        except Exception: pass

class Side(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(120); self.grid = None; self.ibtns = []
        vb = QVBoxLayout(self); vb.setContentsMargins(6,6,6,6); vb.setSpacing(4)
        self.sp = self._sec(PLACE_IMGS); self.sr = self._sec(ROAD_IMGS)
        self.props = QWidget(); self.pvb = QVBoxLayout(self.props)
        self.pvb.setContentsMargins(0,0,0,0); self.pvb.setSpacing(4)
        for w in (self.sp, self.sr, self.props): w.hide(); vb.addWidget(w)
        vb.addStretch()

    def _sec(self, paths):
        w = QWidget(); vb = QVBoxLayout(w); vb.setContentsMargins(0,0,0,0)
        for p in paths:
            b = QPushButton(); b.setFixedSize(100,100); b.setCheckable(True); b.setProperty("path", p)
            ic = get_px(p)
            if not ic.isNull(): b.setIcon(QIcon(ic)); b.setIconSize(QSize(88,88))
            else: b.setText(os.path.basename(p)[:8])
            b.clicked.connect(self._pick); vb.addWidget(b); self.ibtns.append(b)
        return w

    def _pick(self):
        s = self.sender()
        for b in self.ibtns:
            if b is not s: b.setChecked(False)
        if self.grid: self.grid.sel = s.property("path") if s.isChecked() else None

    def switch(self, place=False, road=False):
        for b in self.ibtns: b.setChecked(False)
        if self.grid: self.grid.sel = None; self.grid.mode = 'place' if place else ('road' if road else None)
        self.props.hide(); self.sp.setVisible(place); self.sr.setVisible(road)

    def show_props(self, cell, obj, grid):
        while self.pvb.count():
            w = self.pvb.takeAt(0).widget()
            if w: w.deleteLater()
        self.props.show(); base = obj["base"]
        self.pvb.addWidget(QLabel(f"<b>{os.path.basename(base)}</b>"))
        if base in ROT:
            b = QPushButton("Повернуть")
            b.clicked.connect(lambda: (obj.update(rot=(obj["rot"]+90)%360), grid.update()))
            self.pvb.addWidget(b)
        if base in CYCLES:
            b = QPushButton("Изменить тип"); c = CYCLES[base]
            def color(_, o=obj, cy=c):
                i = cy.index(o["path"]) if o["path"] in cy else 0
                o["path"] = cy[(i+1)%len(cy)]; grid.update()
            b.clicked.connect(color); self.pvb.addWidget(b)
        if base == IMG2:
            lbl = QLabel(f"Скорость: {obj.get('speed',0)} сек"); self.pvb.addWidget(lbl)
            for txt, d in (("+1",1),("-1",-1)):
                b = QPushButton(txt)
                def spd(_, o=obj, dv=d, l=lbl): o["speed"]=o.get("speed",0)+dv; l.setText(f"Скорость: {o['speed']} сек")
                b.clicked.connect(spd); self.pvb.addWidget(b)
        b = QPushButton("Удалить"); b.setStyleSheet("color:red;")
        def dele(_, c=cell, g=grid): g.objs.pop(c,None); g.roads.pop(c,None); g.update(); self.props.hide()
        b.clicked.connect(dele); self.pvb.addWidget(b)

class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Интеллектуальная Дорожная Система")
        lp = QPixmap(LOGO)
        if not lp.isNull(): self.setWindowIcon(QIcon(lp))
        self.side = Side(); self.grid = Grid(self.side); self.side.grid = self.grid

        c = QWidget(); self.setCentralWidget(c)
        root = QVBoxLayout(c); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        body = QHBoxLayout(); body.setContentsMargins(0,0,0,0); body.setSpacing(0)
        body.addWidget(self.side); body.addWidget(self.grid); root.addLayout(body)

        bar = QHBoxLayout(); bar.setContentsMargins(6,6,6,6); bar.setSpacing(6)
        self.bp = QPushButton("Добавить объекты"); self.bp.setCheckable(True)
        self.br = QPushButton("Редактор дороги");  self.br.setCheckable(True)
        bs = QPushButton("Сохранить"); bl = QPushButton("Загрузить")
        self.bp.toggled.connect(lambda v: (self.br.setChecked(False), self.side.switch(place=v)))
        self.br.toggled.connect(lambda v: (self.bp.setChecked(False), self.side.switch(road=v)))
        bs.clicked.connect(lambda: (fn:=QFileDialog.getSaveFileName(self,"","","JSON (*.json)")[0]) and self.grid.save(fn))
        bl.clicked.connect(lambda: (fn:=QFileDialog.getOpenFileName(self,"","","JSON (*.json)")[0]) and self.grid.load(fn))
        for b in (self.bp, self.br, bs, bl):
            b.setFixedHeight(32); b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed); bar.addWidget(b)
        root.addLayout(bar); self.adjustSize()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    App().show()
    sys.exit(app.exec())
