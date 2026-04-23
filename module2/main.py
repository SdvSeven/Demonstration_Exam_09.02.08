# ЧЕРНОВИК ПРОГРАММЫ ДЛЯ МОДУЛЯ 2
import sys, json, os
from PyQt6.QtWidgets import *
from PyQt6.QtGui import QPainter, QColor, QPen, QIcon, QPixmap, QTransform
from PyQt6.QtCore import Qt, QSize, QTimer

M        = r"module1\media"
MAP_FILE = r"map.json"
LOGO     = f"{M}\\TLgreen.png"
IMG1, IMG2, IMG3, IMG4, IMG5 = f"{M}\\Cbottom.png", f"{M}\\Pedestrain.png", f"{M}\\Block.png", f"{M}\\Zhorizontal.png", f"{M}\\TLyellow.png"
RD1, RD2 = f"{M}\\Rvertical.png", f"{M}\\Rcrossroads.png"
PLACE_IMGS = [IMG1, IMG2, IMG3, IMG4, IMG5]
FREE   = {IMG2, IMG3}
ROT    = {IMG1, IMG2, IMG4, IMG5, RD1, RD2}
CYCLES = {
    IMG1: [IMG1, f"{M}\\BCvertical.png", f"{M}\\GCicon.ico"],
    IMG3: [IMG3, f"{M}\\Stop.png",       f"{M}\\Start.png"],
    IMG5: [IMG5, f"{M}\\TLred.png",      f"{M}\\TLgreen.png"],
}
TL_CYCLE = [f"{M}\\TLred.png", f"{M}\\TLyellow.png", f"{M}\\TLgreen.png"]
CELL, COLS, ROWS = 36, 21, 21

def get_px(path, rot=0):
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
                img = get_px(o["path"], o["rot"])
                if not img.isNull():
                    p.drawPixmap(x * CELL, y * CELL, CELL, CELL, img)
        p.setPen(QPen(QColor(0, 0, 0, 50)))
        for i in range(COLS + 1): p.drawLine(i * CELL, 0, i * CELL, ROWS * CELL)
        for i in range(ROWS + 1): p.drawLine(0, i * CELL, COLS * CELL, i * CELL)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton: return
        x, y = int(e.position().x() // CELL), int(e.position().y() // CELL)
        if not (0 <= x < COLS and 0 <= y < ROWS): return
        c = (x, y)
        if self.mode == 'place' and self.sel:
            if c in self.roads or self.sel in FREE:
                self.objs[c] = {"path": self.sel, "base": self.sel, "rot": 0, "speed": 0}
        else:
            o = self.objs.get(c) or self.roads.get(c)
            if o: self.side.show_props(c, o, self)
        self.update()

    def load(self, path):
        try:
            with open(path, encoding="utf-8") as f: data = json.load(f)
            p = lambda d: {tuple(map(int, k.split(","))): v for k, v in d.items()}
            self.roads, self.objs = p(data.get("roads", {})), p(data.get("objs", {}))
            self.update()
        except Exception: pass

class Side(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(120); self.grid = None; self.ibtns = []
        vb = QVBoxLayout(self); vb.setContentsMargins(6, 6, 6, 6); vb.setSpacing(4)
        self.sp = self._sec(PLACE_IMGS)
        self.props = QWidget()
        self.pvb = QVBoxLayout(self.props); self.pvb.setContentsMargins(0, 0, 0, 0); self.pvb.setSpacing(4)
        for w in (self.sp, self.props): w.hide(); vb.addWidget(w)
        vb.addStretch()
        self.mode_lbl = QLabel("Текущий режим:\n—")
        self.mode_lbl.setWordWrap(True)
        self.mode_lbl.setStyleSheet("font-size:10px;color:#444;")
        vb.addWidget(self.mode_lbl)

    def set_mode(self, t): self.mode_lbl.setText(f"Текущий режим:\n{t}")

    def _sec(self, paths):
        w = QWidget(); vb = QVBoxLayout(w); vb.setContentsMargins(0, 0, 0, 0)
        for p in paths:
            b = QPushButton(); b.setFixedSize(100, 100); b.setCheckable(True); b.setProperty("path", p)
            ic = get_px(p)
            if not ic.isNull(): b.setIcon(QIcon(ic)); b.setIconSize(QSize(88, 88))
            else: b.setText(os.path.basename(p)[:8])
            b.clicked.connect(self._pick); vb.addWidget(b); self.ibtns.append(b)
        return w

    def _pick(self):
        s = self.sender()
        for b in self.ibtns:
            if b is not s: b.setChecked(False)
        if self.grid: self.grid.sel = s.property("path") if s.isChecked() else None

    def switch(self, place=False):
        for b in self.ibtns: b.setChecked(False)
        if self.grid: self.grid.sel = None; self.grid.mode = 'place' if place else None
        self.props.hide(); self.sp.setVisible(place)

    def show_props(self, cell, obj, grid):
        while self.pvb.count():
            w = self.pvb.takeAt(0).widget()
            if w: w.deleteLater()
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
            def color(_, o=obj, cy=c):
                i = cy.index(o["path"]) if o["path"] in cy else 0
                o["path"] = cy[(i + 1) % len(cy)]; grid.update()
            b.clicked.connect(color); self.pvb.addWidget(b)
        if base == IMG2:
            lbl = QLabel(f"Скорость: {obj.get('speed', 0)} сек"); self.pvb.addWidget(lbl)
            for txt, d in (("+1", 1), ("-1", -1)):
                b = QPushButton(txt)
                def spd(_, o=obj, dv=d, l=lbl): o["speed"] = o.get("speed", 0) + dv; l.setText(f"Скорость: {o['speed']} сек")
                b.clicked.connect(spd); self.pvb.addWidget(b)
        b = QPushButton("Удалить"); b.setStyleSheet("color:red;")
        def dele(_, c=cell, g=grid): g.objs.pop(c, None); g.roads.pop(c, None); g.update(); self.props.hide()
        b.clicked.connect(dele); self.pvb.addWidget(b)

class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Интеллектуальная Дорожная Система")
        lp = QPixmap(LOGO)
        if not lp.isNull(): self.setWindowIcon(QIcon(lp))
        self.side = Side(); self.grid = Grid(self.side); self.side.grid = self.grid

        self._tl_idx = 0
        self._tl_timer = QTimer(interval=5000, timeout=self._tl_tick)

        c = QWidget(); self.setCentralWidget(c)
        root = QVBoxLayout(c); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        body = QHBoxLayout(); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(0)
        body.addWidget(self.side); body.addWidget(self.grid); root.addLayout(body)

        bar1 = QHBoxLayout(); bar1.setContentsMargins(6, 6, 6, 2); bar1.setSpacing(6)
        self.bp = QPushButton("Добавить объекты"); self.bp.setCheckable(True); self.bp.setFixedHeight(32)
        self.bp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.bp.toggled.connect(lambda v: (self.side.switch(place=v), self.side.set_mode("Добавить объекты" if v else "—")))
        bar1.addWidget(self.bp); root.addLayout(bar1)

        bar2 = QHBoxLayout(); bar2.setContentsMargins(6, 2, 6, 6); bar2.setSpacing(6)
        for name, checkable, slot in [
            ("Диагностика",         False, lambda: self.side.set_mode("Диагностика")),
            ("Восстановление",      False, lambda: self.side.set_mode("Восстановление")),
            ("Старт/Стоп цикла",    False, lambda: self.side.set_mode("Старт/Стоп цикла")),
            ("Режим по времени",    True,  self._toggle_time),
            ("Режим по транспорту", False, lambda: self.side.set_mode("Режим по транспорту")),
            ("Тест шаблон",         False, lambda: self.side.set_mode("Тест шаблон")),
            ("Тест рандом",         False, lambda: self.side.set_mode("Тест рандом")),
            ("Таблицы",             False, lambda: self.side.set_mode("Таблицы")),
        ]:
            b = QPushButton(name); b.setFixedHeight(32); b.setCheckable(checkable)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.clicked.connect(slot); bar2.addWidget(b)
            if checkable: self._btn_time = b
        root.addLayout(bar2); self.adjustSize(); self.grid.load(MAP_FILE)

    def _toggle_time(self):
        if self._btn_time.isChecked():
            self._tl_idx = 0; self._tl_tick(); self._tl_timer.start()
            self.side.set_mode("Режим по времени")
        else:
            self._tl_timer.stop()
            for o in self.grid.objs.values():
                if o["base"] == IMG5: o["path"] = IMG5
            self.grid.update(); self.side.set_mode("—")

    def _tl_tick(self):
        state = TL_CYCLE[self._tl_idx % 3]
        for o in self.grid.objs.values():
            if o["base"] == IMG5: o["path"] = state
        self._tl_idx += 1; self.grid.update()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    App().show()
    sys.exit(app.exec())
