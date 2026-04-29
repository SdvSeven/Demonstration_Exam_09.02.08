import sys, json, os, sqlite3, time
from PyQt6.QtWidgets import *
from PyQt6.QtGui import QPainter, QColor, QPen, QIcon, QPixmap, QTransform
from PyQt6.QtCore import Qt, QSize, QTimer
try: import serial; HAS_SERIAL = True
except: HAS_SERIAL = False

# ── Пути ─────────────────────────────────────────────────────────────────────
M        = r"module1\media"
MAP_FILE = r"map.json"   # автозагрузка карты
DB_FILE  = r"events.db"
LOGO     = f"{M}\\TLgreen.png"
IMG1,IMG2,IMG3,IMG4,IMG5 = f"{M}\\Cbottom.png",f"{M}\\Pedestrain.png",f"{M}\\Block.png",f"{M}\\Zhorizontal.png",f"{M}\\TLyellow.png"
RD1,RD2  = f"{M}\\Rvertical.png",f"{M}\\Rcrossroads.png"

PLACE_IMGS = [IMG1,IMG2,IMG3,IMG4,IMG5,RD1,RD2]
FREE       = {IMG2,IMG3}
ROT        = {IMG1,IMG2,IMG4,IMG5}
CYCLES     = {IMG1:[IMG1,f"{M}\\BCvertical.png",f"{M}\\GCicon.ico"],
              IMG3:[IMG3,f"{M}\\Stop.png",f"{M}\\Start.png"]}
TL_CYCLE   = [f"{M}\\TLred.png",f"{M}\\TLyellow.png",f"{M}\\TLgreen.png"]
ROADS      = {RD1,RD2}
CELL,COLS,ROWS = 36,21,21

# ── БД ───────────────────────────────────────────────────────────────────────
def init_db():
    con = sqlite3.connect(DB_FILE)
    con.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT, event TEXT)")
    con.commit(); con.close()

def log(event):
    con = sqlite3.connect(DB_FILE)
    con.execute("INSERT INTO events(time,event) VALUES(?,?)", (time.strftime("%Y-%m-%d %H:%M:%S"), event))
    con.commit(); con.close()

# ── Arduino ───────────────────────────────────────────────────────────────────
class Arduino:
    def __init__(self, port):
        self._s = None
        if HAS_SERIAL and port:
            try: self._s = serial.Serial(port, 9600, timeout=0.1)
            except: pass
    def tl(self, path):
        cmd = "G" if "green" in path else ("R" if "red" in path else "Y")
        try: self._s and self._s.write(cmd.encode())
        except: pass

ARD = None

# ── Утилиты ───────────────────────────────────────────────────────────────────
get_px  = lambda p,r=0:(lambda px:px.transformed(QTransform().rotate(r)) if r and not px.isNull() else px)(QPixmap(p))
new_obj = lambda p: {"path":p,"base":p,"rot":0,"speed":0}
parse   = lambda d: {tuple(map(int,k.split(","))):v for k,v in d.items()}

# ── Grid ──────────────────────────────────────────────────────────────────────
class Grid(QWidget):
    def __init__(self, side):
        super().__init__()
        self.setFixedSize(COLS*CELL, ROWS*CELL); self.setMouseTracking(True)
        self.side = side; self.roads,self.objs = {},{}; self.mode = self.sel = None
        self._tip = QLabel(self); self._tip.setStyleSheet("background:#555;color:#fff;padding:2px 4px;border-radius:3px;"); self._tip.hide()

    def mouseMoveEvent(self, e):
        x,y = int(e.position().x()//CELL),int(e.position().y()//CELL)
        if 0<=x<COLS and 0<=y<ROWS:
            self._tip.setText(f"x:{x} y:{y}"); self._tip.adjustSize()
            self._tip.move(int(e.position().x())+10, int(e.position().y())+14); self._tip.show()
        else: self._tip.hide()

    def leaveEvent(self, _): self._tip.hide()

    def paintEvent(self, _):
        p = QPainter(self); p.fillRect(self.rect(), QColor(235,235,235))
        for layer in (self.roads, self.objs):
            for (x,y),o in layer.items():
                img = get_px(o["path"], o["rot"])
                if not img.isNull(): p.drawPixmap(x*CELL,y*CELL,CELL,CELL,img)
        p.setPen(QPen(QColor(0,0,0,50)))
        for i in range(COLS+1): p.drawLine(i*CELL,0,i*CELL,ROWS*CELL)
        for i in range(ROWS+1): p.drawLine(0,i*CELL,COLS*CELL,i*CELL)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton: return
        x,y = int(e.position().x()//CELL),int(e.position().y()//CELL)
        if not (0<=x<COLS and 0<=y<ROWS): return
        c = (x,y)
        if self.mode == 'place' and self.sel:
            layer = self.roads if self.sel in ROADS else self.objs
            if c in self.roads or self.sel in FREE|ROADS:
                layer[c] = new_obj(self.sel)
        else:
            o = self.objs.get(c) or self.roads.get(c)
            if o: self.side.show_props(c, o, self)
        self.update()

    def save(self, path):
        ser = lambda d: {f"{k[0]},{k[1]}":v for k,v in d.items()}
        with open(path,"w",encoding="utf-8") as f:
            json.dump({"roads":ser(self.roads),"objs":ser(self.objs)}, f, indent=2)

    def load(self, path):
        try:
            with open(path,encoding="utf-8") as f: data = json.load(f)
            self.roads,self.objs = parse(data.get("roads",{})),parse(data.get("objs",{}))
        except Exception: pass

# ── Side ──────────────────────────────────────────────────────────────────────
class Side(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(120); self.grid = None; self.ibtns = []
        self._auto_timer = QTimer(interval=3000, timeout=self._auto_tick)
        self._auto_obj = self._auto_grid = None
        vb = QVBoxLayout(self); vb.setContentsMargins(6,6,6,6); vb.setSpacing(4)
        self.sp = self._sec(PLACE_IMGS)
        self.props = QWidget(); self.pvb = QVBoxLayout(self.props)
        self.pvb.setContentsMargins(0,0,0,0); self.pvb.setSpacing(4)
        for w in (self.sp, self.props): w.hide(); vb.addWidget(w)
        vb.addStretch()

    def _sec(self, paths):
        w = QWidget(); vb = QVBoxLayout(w); vb.setContentsMargins(0,0,0,0)
        for p in paths:
            b = QPushButton(); b.setFixedSize(100,100); b.setCheckable(True); b.setProperty("path",p)
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

    def switch(self, place=False):
        for b in self.ibtns: b.setChecked(False)
        if self.grid: self.grid.sel = None; self.grid.mode = 'place' if place else None
        self.props.hide(); self.sp.setVisible(place)

    def _btn(self, label, slot, checkable=False):
        b = QPushButton(label); b.setCheckable(checkable); b.clicked.connect(slot)
        self.pvb.addWidget(b); return b

    def show_props(self, cell, obj, grid):
        self._auto_timer.stop()
        while self.pvb.count():
            w = self.pvb.takeAt(0).widget()
            if w: w.deleteLater()
        self.props.show(); base = obj["base"]
        self.pvb.addWidget(QLabel(f"<b>{os.path.basename(base)}</b>"))

        if base in ROT:
            self._btn("Повернуть", lambda: (obj.update(rot=(obj["rot"]+90)%360), grid.update()))

        if base in CYCLES:
            c = CYCLES[base]
            def chg_type(_,o=obj,cy=c):
                i = cy.index(o["path"]) if o["path"] in cy else 0
                o["path"] = cy[(i+1)%len(cy)]; grid.update()
            self._btn("Изменить тип", chg_type)

        if base == IMG5:  # светофор
            def manual(_,o=obj,g=grid):
                o["path"] = TL_CYCLE[(TL_CYCLE.index(o["path"])+1) % 3] if o["path"] in TL_CYCLE else TL_CYCLE[0]
                if ARD: ARD.tl(o["path"])
                log(f"Ручной: {os.path.basename(o['path'])}"); g.update()
            self._btn("Ручной режим", manual)

            def auto_toggle(checked, o=obj, g=grid):
                if checked: self._auto_obj=o; self._auto_grid=g; self._auto_timer.start(); log("Авторежим вкл")
                else: self._auto_timer.stop(); log("Авторежим выкл")
            self._btn("Автоматический режим", auto_toggle, checkable=True)

        if base == IMG2:
            lbl = QLabel(f"Скорость: {obj.get('speed',0)} сек"); self.pvb.addWidget(lbl)
            for txt,d in (("+1",1),("-1",-1)):
                def spd(_,o=obj,dv=d,l=lbl): o["speed"]=o.get("speed",0)+dv; l.setText(f"Скорость: {o['speed']} сек")
                self._btn(txt, spd)

        def dele(_,c=cell,g=grid):
            g.objs.pop(c,None); g.roads.pop(c,None); g.update(); self.props.hide(); self._auto_timer.stop()
        b = self._btn("Удалить", dele); b.setStyleSheet("color:red;")

    def _auto_tick(self):
        if not self._auto_obj: return
        o = self._auto_obj
        o["path"] = TL_CYCLE[(TL_CYCLE.index(o["path"])+1) % 3] if o["path"] in TL_CYCLE else TL_CYCLE[0]
        if self._auto_grid: self._auto_grid.update()
        if ARD: ARD.tl(o["path"])
        log(f"Авто: {os.path.basename(o['path'])}")

# ── App ───────────────────────────────────────────────────────────────────────
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
        bs = QPushButton("Сохранить"); bl = QPushButton("Загрузить")
        self.bp.toggled.connect(lambda v: self.side.switch(place=v))
        bs.clicked.connect(lambda: (fn:=QFileDialog.getSaveFileName(self,"","","JSON (*.json)")[0]) and self.grid.save(fn))
        bl.clicked.connect(lambda: (fn:=QFileDialog.getOpenFileName(self,"","","JSON (*.json)")[0]) and (self.grid.load(fn), self.grid.update()))
        for b in (self.bp, bs, bl):
            b.setFixedHeight(32); b.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed); bar.addWidget(b)
        root.addLayout(bar); self.adjustSize()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    init_db()
    port, ok = QInputDialog.getText(None, "Arduino", "COM-порт (или пусто):")
    ARD = Arduino(port.strip() if ok and port.strip() else None)
    w = App(); w.show()
    QTimer.singleShot(0, lambda: (w.grid.load(MAP_FILE), w.grid.update()))
    sys.exit(app.exec())
