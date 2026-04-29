import sys, json, os, sqlite3, time                          
from PyQt6.QtWidgets import *                               
from PyQt6.QtGui import QPainter, QColor, QPen, QIcon, QPixmap, QTransform  
from PyQt6.QtCore import Qt, QTimer                          
try: import serial; HAS_SERIAL = True                        
except: HAS_SERIAL = False                                   

# ── Константы ────────────────────────────────────────────────────────────────
M        = r"module1\media"                                  # путь к ресурсам
MAP_FILE = r"map.json"                                       # файл карты
DB_FILE  = r"events.db"                                      # файл БД логов
LOGO     = f"{M}\\TLgreen.png"                               # иконка приложения
IMG1,IMG2,IMG3,IMG4,IMG5 = f"{M}\\Cbottom.png",f"{M}\\Pedestrain.png",f"{M}\\Block.png",f"{M}\\Zhorizontal.png",f"{M}\\TLyellow.png"  # объекты
RD1,RD2  = f"{M}\\Rvertical.png",f"{M}\\Rcrossroads.png"     # дороги
TL_RED,TL_YELLOW,TL_GREEN = f"{M}\\TLred.png",f"{M}\\TLyellow.png",f"{M}\\TLgreen.png"  # состояния светофора
TL_CYCLE = [TL_RED, TL_YELLOW, TL_GREEN]                     # цикл светофора
TL_CMD   = {TL_RED: b"R", TL_YELLOW: b"Y", TL_GREEN: b"G"}   # команды Arduino
ROADS    = {RD1, RD2}                                        # множество дорог
FREE     = {IMG2, IMG3}                                      # объекты, которые можно ставить поверх
ROT      = {IMG1, IMG2, IMG4, IMG5}                          # вращаемые объекты
CYCLES   = {IMG1: [IMG1, f"{M}\\BCvertical.png", f"{M}\\GCicon.ico"],  # циклы смены типов
            IMG3: [IMG3, f"{M}\\Stop.png", f"{M}\\Start.png"]}
OBJECTS  = {IMG1:"Машина", IMG2:"Пешеход", IMG3:"Знак", IMG4:"Зебра",  # названия объектов
            IMG5:"Светофор", RD1:"Дорога", RD2:"Перекрёсток"}
CELL,COLS,ROWS = 36,21,21                                   # размер сетки

# ── БД и лог ─────────────────────────────────────────────────────────────────
def init_db():
    con = sqlite3.connect(DB_FILE)                           # подключение к БД
    con.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT, event TEXT)")  # создание таблицы
    con.commit(); con.close()                                # сохранение и закрытие

def log(event):
    con = sqlite3.connect(DB_FILE)                           # подключение к БД
    con.execute("INSERT INTO events(time,event) VALUES(?,?)", (time.strftime("%Y-%m-%d %H:%M:%S"), event))  # запись события
    con.commit(); con.close()                                # сохранение и закрытие

# ── Arduino ───────────────────────────────────────────────────────────────────
class Arduino:
    def __init__(self, port):
        self._s = None                                       # объект serial
        if HAS_SERIAL and port:                              # если есть библиотека и порт
            try: self._s = serial.Serial(port, 9600, timeout=1); time.sleep(2)  # подключение
            except Exception as e: print(f"Arduino: {e}")     # ошибка подключения

    def send_tl(self, path):
        if cmd := TL_CMD.get(path):                          # получение команды по состоянию
            try: self._s and self._s.write(cmd) and self._s.flush()  # отправка в порт
            except Exception as e: print(f"Serial: {e}")      # ошибка отправки

ARD = None                                                   # глобальный объект Arduino

# ── Утилиты ───────────────────────────────────────────────────────────────────
def get_px(path, rot=0):
    px = QPixmap(path)                                       # загрузка изображения
    return px.transformed(QTransform().rotate(rot)) if rot and not px.isNull() else px  # поворот если нужно

new_obj    = lambda p: {"path": p, "base": p, "rot": 0}      # создание объекта
parse_dict = lambda d: {tuple(map(int, k.split(","))): v for k, v in d.items()}  # преобразование ключей

# ── Grid ──────────────────────────────────────────────────────────────────────
class Grid(QWidget):
    def __init__(self, props):
        super().__init__()
        self.setFixedSize(COLS*CELL, ROWS*CELL); self.setMouseTracking(True)  # размер и отслеживание мыши
        self.props = props; self.roads = {}; self.objs = {}  # слои карты
        self.mode  = None; self.sel = None                   # режим и выбранный объект
        self._tip  = QLabel(self)                            # тултип координат
        self._tip.setStyleSheet("background:#444;color:#fff;padding:2px 5px;border-radius:3px;")
        self._tip.hide()

    def mouseMoveEvent(self, e):
        x,y = int(e.position().x()//CELL), int(e.position().y()//CELL)  # координаты ячейки
        if 0 <= x < COLS and 0 <= y < ROWS:
            self._tip.setText(f"x:{x} y:{y}"); self._tip.adjustSize()  # обновление текста
            self._tip.move(int(e.position().x())+10, int(e.position().y())+14); self._tip.show()  # позиция
        else: self._tip.hide()                            # скрыть если вне сетки

    def leaveEvent(self, _): self._tip.hide()              # скрыть при выходе мыши

    def paintEvent(self, _):
        p = QPainter(self); p.fillRect(self.rect(), QColor(235,235,235))  # фон
        for layer in (self.roads, self.objs):             # отрисовка слоёв
            for (x,y),o in layer.items():
                img = get_px(o["path"], o.get("rot",0))  # получить изображение
                if not img.isNull(): p.drawPixmap(x*CELL, y*CELL, CELL, CELL, img)  # отрисовать
        p.setPen(QPen(QColor(0,0,0,50)))                  # сетка
        for i in range(COLS+1): p.drawLine(i*CELL,0,i*CELL,ROWS*CELL)
        for i in range(ROWS+1): p.drawLine(0,i*CELL,COLS*CELL,i*CELL)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton: return  # только ЛКМ
        x,y = int(e.position().x()//CELL), int(e.position().y()//CELL)
        if not (0 <= x < COLS and 0 <= y < ROWS): return    # проверка границ
        c = (x,y)
        if self.mode == 'place' and self.sel:               # режим размещения
            layer = self.roads if self.sel in ROADS else self.objs  # выбор слоя
            if c in self.roads or self.sel in FREE|ROADS: layer[c] = new_obj(self.sel)  # размещение
        else:
            o = self.objs.get(c) or self.roads.get(c)       # выбор объекта
            if o: self.props.show_props(c, o, self)         # показать свойства
        self.update()                                       # перерисовка

    def save(self, path):
        ser = lambda d: {f"{k[0]},{k[1]}": v for k,v in d.items()}  # сериализация ключей
        with open(path,"w",encoding="utf-8") as f:
            json.dump({"roads": ser(self.roads), "objs": ser(self.objs)}, f, indent=2)  # сохранение

    def load(self, path):
        try:
            with open(path,encoding="utf-8") as f: data = json.load(f)  # загрузка JSON
            self.roads = parse_dict(data.get("roads",{}))              # восстановление
            self.objs  = parse_dict(data.get("objs", {}))
        except Exception: pass                                         # игнор ошибок

# ── PropsPanel ────────────────────────────────────────────────────────────────
class PropsPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._auto_obj  = None; self._auto_grid = None       # объекты для авто режима
        self._timer = QTimer(interval=3000, timeout=self._auto_tick)  # таймер
        self._vb = QVBoxLayout(self)
        self._vb.setContentsMargins(4,4,4,4); self._vb.setSpacing(4)
        self.hide()

    def _clear(self):
        while self._vb.count():                             # очистка панели
            w = self._vb.takeAt(0).widget()
            if w: w.deleteLater()

    def _btn(self, label, slot, checkable=False):
        b = QPushButton(label); b.setCheckable(checkable)   # создание кнопки
        b.clicked.connect(slot); self._vb.addWidget(b); return b

    def show_props(self, cell, obj, grid):
        self._timer.stop(); self._clear(); self.show()      # подготовка панели
        base = obj["base"]
        self._vb.addWidget(QLabel(f"<b>{OBJECTS.get(base, os.path.basename(base))}</b>"))  # название

        if base in ROT:
            self._btn("Повернуть", lambda: (obj.update(rot=(obj.get("rot",0)+90)%360), grid.update()))  # вращение

        if base in CYCLES:
            cy = CYCLES[base]
            def on_type(_, o=obj, c=cy):
                i = c.index(o["path"]) if o["path"] in c else 0
                o["path"] = c[(i+1)%len(c)]; grid.update()  # смена типа
            self._btn("Изменить тип", on_type)

        if base == IMG5:
            def on_manual(_, o=obj, g=grid):
                idx = TL_CYCLE.index(o["path"]) if o["path"] in TL_CYCLE else 0
                o["path"] = TL_CYCLE[(idx+1)%3]             # смена состояния
                if ARD: ARD.send_tl(o["path"])              # отправка в Arduino
                log(f"Ручной: {os.path.basename(o['path'])}"); g.update()
            self._btn("Ручной режим", on_manual)

            def on_auto(checked, o=obj, g=grid):
                if checked: self._auto_obj=o; self._auto_grid=g; self._timer.start(); log("Авторежим вкл")  # старт
                else: self._timer.stop(); log("Авторежим выкл")  # стоп
            self._btn("Автоматический режим", on_auto, checkable=True)

        def on_del(_, c=cell, g=grid):
            g.objs.pop(c,None); g.roads.pop(c,None); g.update(); self.hide(); self._timer.stop()  # удаление
        self._btn("Удалить", on_del).setStyleSheet("color:red;")

    def _auto_tick(self):
        if not self._auto_obj: return                        # если нет объекта
        o = self._auto_obj
        o["path"] = TL_CYCLE[(TL_CYCLE.index(o["path"])+1)%3] if o["path"] in TL_CYCLE else TL_CYCLE[0]  # цикл
        if self._auto_grid: self._auto_grid.update()
        if ARD: ARD.send_tl(o["path"])
        log(f"Авто: {os.path.basename(o['path'])}")

# ── App ───────────────────────────────────────────────────────────────────────
class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Интеллектуальная Дорожная Система")  # заголовок
        lp = QPixmap(LOGO)
        if not lp.isNull(): self.setWindowIcon(QIcon(lp))         # иконка

        self.pp   = PropsPanel()                                  # панель свойств
        self.grid = Grid(self.pp)                                 # сетка

        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        body = QHBoxLayout(); body.setContentsMargins(0,0,0,0); body.setSpacing(0)
        body.addWidget(self.grid); body.addWidget(self.pp)
        root.addLayout(body)

        self._obj_bar = QWidget()                                 # панель объектов
        obj_row = QHBoxLayout(self._obj_bar)
        obj_row.setContentsMargins(4,2,4,2); obj_row.setSpacing(4)
        self._obj_btns = []
        for path,name in OBJECTS.items():
            b = QPushButton(name); b.setCheckable(True); b.setFixedHeight(28)
            b.setProperty("path", path); b.clicked.connect(self._on_obj_btn)
            obj_row.addWidget(b); self._obj_btns.append(b)
        self._obj_bar.hide(); root.addWidget(self._obj_bar)

        bar = QHBoxLayout(); bar.setContentsMargins(6,6,6,6); bar.setSpacing(6)  # нижняя панель
        self.bp = QPushButton("Добавить объекты"); self.bp.setCheckable(True)
        self.bp.toggled.connect(self._toggle_place)
        bs = QPushButton("Сохранить"); bs.clicked.connect(self._save)
        bl = QPushButton("Загрузить");  bl.clicked.connect(self._load)
        for b in (self.bp, bs, bl):
            b.setFixedHeight(32); b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            bar.addWidget(b)
        root.addLayout(bar); self.adjustSize()

    def _toggle_place(self, on):
        self._obj_bar.setVisible(on)                           # показать/скрыть панель
        self.grid.mode = 'place' if on else None               # режим
        if not on: self.grid.sel = None; [b.setChecked(False) for b in self._obj_btns]

    def _on_obj_btn(self):
        s = self.sender()
        [b.setChecked(False) for b in self._obj_btns if b is not s]  # снять выбор с других
        self.grid.sel = s.property("path") if s.isChecked() else None  # выбранный объект

    def _save(self):
        fn,_ = QFileDialog.getSaveFileName(self,"","","JSON (*.json)")  # диалог сохранения
        if fn: self.grid.save(fn)

    def _load(self):
        fn,_ = QFileDialog.getOpenFileName(self,"","","JSON (*.json)")  # диалог загрузки
        if fn: self.grid.load(fn); self.grid.update()

# ── Запуск ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)                             # создание приложения
    init_db()                                                # инициализация БД
    port,ok = QInputDialog.getText(None, "Arduino", "COM-порт\nПример: COM3")  # ввод порта
    ARD = Arduino(port.strip() if ok and port.strip() else None)  # создание Arduino
    w = App(); w.show()                                      # запуск окна
    QTimer.singleShot(0, lambda: (w.grid.load(MAP_FILE), w.grid.update()))  # загрузка карты
    sys.exit(app.exec())                                     # запуск цикла Qt
