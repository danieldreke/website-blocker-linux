import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, GLib
import re
import select
import shlex
import subprocess
import tempfile
import threading
import os

DEBUG = 0

WINDOW_WIDTH = 400
WINDOW_HEIGHT = 300

HOSTS_FILEPATH = "/etc/hosts"
MARKER_START = "# --- Website Blocker START ---"
MARKER_END = "# --- Website Blocker END ---"
LOOPBACK_IP = "127.0.0.1"


def parse_domain(line):
    if line.startswith(f"{LOOPBACK_IP} "):
        return line[len(LOOPBACK_IP) + 1:]
    return line


def load():
    rows = []
    if not os.path.exists(HOSTS_FILEPATH):
        return rows

    with open(HOSTS_FILEPATH) as f:
        content = f.read()

    match = re.search(
        rf"{re.escape(MARKER_START)}(.*?){re.escape(MARKER_END)}",
        content, flags=re.DOTALL
    )
    if not match:
        return rows

    lines = [l for l in match.group(1).splitlines() if l.strip()]

    for line in lines:
        if line.startswith("# "):
            inner = parse_domain(line[2:])
            if not inner.startswith("www."):
                rows.append((False, inner))
        else:
            domain = parse_domain(line)
            if not domain.startswith("www."):
                rows.append((True, domain))
    return rows


def apply_to_hosts(rows, root_proc=None):
    with open(HOSTS_FILEPATH) as f:
        content = f.read()

    content = re.sub(
        rf"\n?{re.escape(MARKER_START)}.*?{re.escape(MARKER_END)}\n?",
        "", content, flags=re.DOTALL
    )

    block = [MARKER_START]
    for enabled, site in rows:
        block.append(f"{LOOPBACK_IP} {site}" if enabled else f"# {LOOPBACK_IP} {site}")
        block.append(f"{LOOPBACK_IP} www.{site}" if enabled else f"# {LOOPBACK_IP} www.{site}")
    block.append(MARKER_END)
    block.append("")

    new_content = content.rstrip("\n") + "\n\n" + "\n".join(block) + "\n"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".hosts", delete=False) as tmp:
        tmp.write(new_content)
        tmp_path = tmp.name

    if os.geteuid() == 0:
        with open(HOSTS_FILEPATH, "w") as f:
            f.write(new_content)
        success = True
    elif root_proc and root_proc.poll() is None:
        cmd = f"cp {shlex.quote(tmp_path)} {shlex.quote(HOSTS_FILEPATH)} && echo __OK__ || echo __FAIL__\n"
        root_proc.stdin.write(cmd.encode())
        root_proc.stdin.flush()
        ready, _, _ = select.select([root_proc.stdout], [], [], 5)
        success = b"__OK__" in root_proc.stdout.readline() if ready else False
    else:
        result = subprocess.run(["pkexec", "cp", tmp_path, HOSTS_FILEPATH])
        success = result.returncode == 0

    os.unlink(tmp_path)
    return success


class App(Gtk.Window):
    def __init__(self):
        super().__init__(title="Website Blocker")
        self.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(10)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(box)

        self._unsaved_changes = False
        self._root_proc = None
        self._unlocked = False
        self.store = Gtk.ListStore(bool, str)
        for row in load():
            self.store.append(list(row))
        self.store.set_sort_column_id(1, Gtk.SortType.ASCENDING)

        self.treeview = Gtk.TreeView(model=self.store)
        treeview = self.treeview
        treeview.set_headers_visible(True)
        treeview.connect("motion-notify-event", self.on_mouse_motion)

        toggle_renderer = Gtk.CellRendererToggle()
        toggle_renderer.set_property("activatable", False)
        toggle_renderer.set_property("sensitive", False)
        toggle_renderer.connect("toggled", self.on_toggled)
        self.toggle_col = Gtk.TreeViewColumn("Block", toggle_renderer, active=0)
        self.toggle_renderer = toggle_renderer
        treeview.append_column(self.toggle_col)

        self._editing_path = None
        self._pending_text = None
        self.prefix_renderer = Gtk.CellRendererText()
        self.text_renderer = Gtk.CellRendererText()
        self.text_renderer.set_property("editable", False)
        self.text_renderer.connect("edited", self.on_edited)
        self.text_renderer.connect("editing-started", self.on_editing_started)
        self.site_col = Gtk.TreeViewColumn("Website")
        self.site_col.pack_start(self.prefix_renderer, False)
        self.site_col.pack_start(self.text_renderer, True)
        self.site_col.set_expand(True)
        self.site_col.set_cell_data_func(self.prefix_renderer, self._www_prefix_func)
        self.site_col.set_cell_data_func(self.text_renderer, self._domain_text_func)
        treeview.append_column(self.site_col)


        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_vexpand(True)
        self.scroll.set_min_content_height(WINDOW_HEIGHT // 2)
        self.scroll.add(treeview)
        box.pack_start(self.scroll, True, True, 0)

        self.status_label = Gtk.Label(label="")
        self.status_label.set_xalign(0)
        self.status_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.status_label.set_max_width_chars(1)
        self.status_label.set_lines(1)
        self.status_label.set_single_line_mode(True)
        box.pack_start(self.status_label, False, False, 0)

        btn_box = Gtk.Box(spacing=6)
        box.pack_start(btn_box, False, False, 0)

        btn_size_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)

        self.unlock_btn = self._icon_button("Unlock", "\U0001F512")
        self.unlock_btn.connect("clicked", self.on_unlock)
        btn_box.pack_start(self.unlock_btn, False, False, 0)
        btn_size_group.add_widget(self.unlock_btn)

        self.add_btn = self._icon_button("Add", "list-add")
        self.add_btn.connect("clicked", self.on_add)
        self.add_btn.set_sensitive(False)
        btn_box.pack_start(self.add_btn, False, False, 0)
        btn_size_group.add_widget(self.add_btn)

        self.remove_btn = self._icon_button("Remove", "list-remove")
        self.remove_btn.connect("clicked", self.on_remove)
        self.remove_btn.set_sensitive(False)
        btn_box.pack_start(self.remove_btn, False, False, 0)
        btn_size_group.add_widget(self.remove_btn)

        spacer = Gtk.Box()
        btn_box.pack_start(spacer, True, True, 0)

        close_btn = self._icon_button("Close", "window-close")
        close_btn.connect("clicked", lambda _: self.do_close())
        btn_box.pack_start(close_btn, False, False, 0)
        btn_size_group.add_widget(close_btn)
        box.set_focus_chain([btn_box, self.scroll])
        self.connect("delete-event", lambda w, e: not self.do_close())
        if os.geteuid() == 0:
            self._on_unlocked()
        else:
            self.set_status("Click \U0001F512 Unlock to make changes.")
            GLib.idle_add(self.unlock_btn.grab_focus)

    def _set_btn_content(self, btn, label, icon_name):
        old = btn.get_child()
        btn.remove(old)
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        inner.set_halign(Gtk.Align.CENTER)
        inner.pack_start(self._make_icon(icon_name), False, False, 0)
        inner.pack_start(Gtk.Label(label=label), False, False, 0)
        btn.add(inner)
        inner.show_all()

    def _revoke_root(self):
        if self._root_proc and self._root_proc.poll() is None:
            self._root_proc.stdin.close()
        self._root_proc = None
        self._unlocked = False
        self.add_btn.set_sensitive(False)
        self.remove_btn.set_sensitive(False)
        self.toggle_renderer.set_property("activatable", False)
        self.toggle_renderer.set_property("sensitive", False)
        self.text_renderer.set_property("editable", False)
        self.treeview.queue_draw()
        self._set_btn_content(self.unlock_btn, "Unlock", "\U0001F512")

    def on_unlock(self, _):
        if self._root_proc and self._root_proc.poll() is None:
            self._revoke_root()
            self.set_status("Root access revoked.")
        else:
            self.unlock_btn.set_sensitive(False)
            self.set_status("Waiting for authentication…")
            threading.Thread(target=self._unlock_thread, daemon=True).start()

    def _unlock_thread(self):
        proc = subprocess.Popen(
            ["pkexec", "/bin/bash"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        proc.stdin.write(b"echo __READY__\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if b"__READY__" in line and proc.poll() is None:
            self._root_proc = proc
            GLib.idle_add(self._on_unlocked)
        else:
            GLib.idle_add(self._on_unlock_failed)

    def _on_unlocked(self):
        self._unlocked = True
        self.add_btn.set_sensitive(True)
        self.remove_btn.set_sensitive(True)
        self.toggle_renderer.set_property("activatable", True)
        self.toggle_renderer.set_property("sensitive", True)
        self.text_renderer.set_property("editable", True)
        self.treeview.queue_draw()
        self._set_btn_content(self.unlock_btn, "Lock", "\U0001F513")
        self.unlock_btn.set_sensitive(True)
        self.set_status("Root access unlocked.")
        return False

    def _on_unlock_failed(self):
        self.unlock_btn.set_sensitive(True)
        self.unlock_btn.grab_focus()
        self.set_status("Authentication cancelled.")
        return False

    def _autosave(self):
        rows = [(row[0], row[1]) for row in self.store]
        if apply_to_hosts(rows, root_proc=self._root_proc):
            self._unsaved_changes = False
            self.set_status(f"Saved to <i>{GLib.markup_escape_text(HOSTS_FILEPATH)}</i>. Please clear your browser cache.", markup=True)
            return True
        else:
            self.set_status(f"Failed to save to <i>{GLib.markup_escape_text(HOSTS_FILEPATH)}</i>", markup=True)
            return False

    def on_toggled(self, _, path):
        self.store[path][0] = not self.store[path][0]
        self._unsaved_changes = True
        if not self._autosave():
            self.store[path][0] = not self.store[path][0]
            self._unsaved_changes = False

    def on_mouse_motion(self, widget, event):
        from gi.repository import Gdk
        result = widget.get_path_at_pos(int(event.x), int(event.y))
        if result and result[1] is self.toggle_col:
            cursor = Gdk.Cursor.new_from_name(widget.get_display(), "pointer")
        else:
            cursor = None
        widget.get_window().set_cursor(cursor)

    def _www_prefix_func(self, col, cell, model, it, _):
        cell.set_property("text", "[www.]")
        cell.set_property("sensitive", self._unlocked and model.get_value(it, 0))

    def _domain_text_func(self, col, cell, model, it, _):
        cell.set_property("text", model.get_value(it, 1))
        cell.set_property("sensitive", self._unlocked and model.get_value(it, 0))

    def on_editing_started(self, _, editable, path):
        self._editing_path = path
        if self._pending_text is not None:
            text = self._pending_text
            self._pending_text = None
            def restore():
                editable.set_text(text)
                editable.set_position(len(text))
                return False
            GLib.idle_add(restore)
        editable.connect("key-press-event", self.on_edit_key)

    def on_edit_key(self, _, event):
        from gi.repository import Gdk
        if event.keyval == Gdk.KEY_Escape:
            path = self._editing_path
            if path and not self.store[path][1]:
                self.store.remove(self.store.get_iter(Gtk.TreePath(path)))

    _domain_re = re.compile(
        r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    )

    def on_edited(self, _, path, new_text):
        def restart_edit():
            self.treeview.set_cursor(Gtk.TreePath(path), self.site_col, True)
            return False

        def reject(msg, markup=False):
            self.set_status(msg, markup=markup)
            self._pending_text = new_text
            GLib.idle_add(restart_edit)

        if not new_text.strip():
            reject("Empty entry rejected.")
            return
        if not self._domain_re.match(new_text.strip()):
            reject(f"<i>{GLib.markup_escape_text(new_text)}</i> is not a valid domain.", markup=True)
            return
        for i, row in enumerate(self.store):
            if row[1] == new_text and str(i) != path:
                reject(f"<i>{GLib.markup_escape_text(new_text)}</i> already exists.", markup=True)
                return
        is_new = not self.store[path][1]
        self.store[path][1] = new_text
        self._unsaved_changes = True
        self._autosave()

    def on_add(self, _):
        it = self.store.append([True, ""])
        path = self.store.get_path(it)
        self.treeview.set_cursor(path, self.site_col, True)

    def on_remove(self, _):
        model, it = self.treeview.get_selection().get_selected()
        if not it:
            return
        site = model[it][1]
        dialog = Gtk.MessageDialog(
            parent=self,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=f"Remove {site}?",
        )
        dialog.add_button("Yes", Gtk.ResponseType.YES)
        dialog.add_button("No", Gtk.ResponseType.NO)
        if dialog.run() == Gtk.ResponseType.YES:
            model.remove(it)
            self._unsaved_changes = True
            self._autosave()
        dialog.destroy()

    def do_close(self):
        if self._unsaved_changes:
            dialog = Gtk.MessageDialog(
                parent=self,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.NONE,
                text="You have unsaved changes. Close anyway?",
            )
            dialog.add_button("Yes", Gtk.ResponseType.YES)
            dialog.add_button("No", Gtk.ResponseType.NO)
            confirmed = dialog.run() == Gtk.ResponseType.YES
            dialog.destroy()
            if not confirmed:
                return False
        self._revoke_root()
        Gtk.main_quit()
        return True

    def set_status(self, message, markup=False):
        if markup:
            self.status_label.set_markup(message)
        else:
            self.status_label.set_text(message)

    def _make_icon(self, icon_name):
        if icon_name.isascii():
            return Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
        return Gtk.Label(label=icon_name)

    def _icon_button(self, label, icon_name):
        btn = Gtk.Button()
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        inner.set_halign(Gtk.Align.CENTER)
        inner.pack_start(self._make_icon(icon_name), False, False, 0)
        inner.pack_start(Gtk.Label(label=label), False, False, 0)
        btn.add(inner)
        return btn


def on_resize(window, event):
    if DEBUG:
        win.set_status(f"Window size: {event.width}×{event.height}")

win = App()
win.connect("destroy", Gtk.main_quit)
win.connect("configure-event", on_resize)
win.show_all()
if DEBUG:
    w, h = win.get_size()
    win.set_status(f"Window size: {w}×{h}")
Gtk.main()
