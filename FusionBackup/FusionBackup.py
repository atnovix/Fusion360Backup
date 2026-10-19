"""
FusionBackup: exporteert alle Fusion-data naar een lokale map, met dezelfde
mappenstructuur als in het Fusion Data Panel.

Per bestandstype:
  ontwerp (f3d)   -> .f3d (of .f3z als het ontwerp naar andere ontwerpen linkt) + .step
  tekening (f2d)  -> .pdf
  overige         -> directe download van het bestand zoals het in de cloud staat
                     (electronics, PDF's, afbeeldingen, uploads, ...)

Opnieuw draaien is veilig: wat al bestaat wordt overgeslagen. Crasht Fusion
halverwege, start het script dan gewoon opnieuw.

Gebaseerd op https://github.com/aconz2/Fusion360Exporter (public domain).
"""
import adsk.core
import adsk.fusion
import adsk.drawing
import traceback
import hashlib
import csv
import os
import re
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- instellingen
EXPORT_ROOT = Path(r'D:\Fusion360')

EXPORT_F3D = True     # native Fusion-archief, met tijdlijn, sketches, CAM, enz.
EXPORT_STEP = True    # neutraal formaat, ook te openen zonder Fusion
EXPORT_PDF = True     # tekeningen (f2d)
DOWNLOAD_OTHER = True  # electronics, uploads en andere niet-ontwerp bestanden
UNHIDE_ALL_FOR_STEP = True  # verborgen bodies/componenten meenemen in de STEP

# Projecten of mappen overslaan (naam, hoofdletterongevoelig). Leeg = alles.
# Voorbeeld: SKIP_PROJECTS = ['Libraries']   SKIP_FOLDERS = ['Electronics Library']
SKIP_PROJECTS = []
SKIP_FOLDERS = []
# -----------------------------------------------------------------------------

app = adsk.core.Application.get()
ui = app.userInterface
log_fh = None
report_fh = None
report = None


def log(*args):
    print(*args, file=log_fh)
    log_fh.flush()


def sanitize(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip().rstrip('.')
    return cleaned or '_'


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:6]


def nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def set_mtime(path: Path, file: adsk.core.DataFile):
    try:
        os.utime(path, (file.dateModified, file.dateModified))
    except Exception:
        pass


class Item:
    """Eén cloudbestand met het geplande doelpad (zonder extensie)."""

    def __init__(self, hub, project, rel_dir: Path, file: adsk.core.DataFile):
        self.hub = hub
        self.project = project
        self.rel_dir = rel_dir
        self.file = file
        self.ext = (file.fileExtension or '').lower()
        self.stem = sanitize(file.name)
        self.renamed = False

    @property
    def kind(self):
        if self.ext == 'f3d':
            return 'design'
        if self.ext == 'f2d':
            return 'drawing'
        return 'other'

    def out_exts(self):
        if self.kind == 'design':
            return ['f3d', 'step']
        if self.kind == 'drawing':
            return ['pdf']
        return [self.ext]

    def base(self) -> Path:
        return EXPORT_ROOT / self.rel_dir / self.stem

    def other_path(self) -> Path:
        # uploads hebben soms al de extensie in de naam
        if self.ext and self.stem.lower().endswith('.' + self.ext):
            return self.base()
        return self.base().with_name(f'{self.stem}.{self.ext}' if self.ext else self.stem)


def path_with(item: Item, ext: str) -> Path:
    return item.base().with_name(f'{item.stem}.{ext}')


def collect(folder, rel_dir: Path, hub, project, items, skipped_folders):
    files = list(folder.dataFiles)
    folder_items = [Item(hub, project, rel_dir, f) for f in files]

    # Fusion staat dubbele namen toe, Windows niet (en is hoofdletterongevoelig).
    seen = {}
    for it in folder_items:
        for e in it.out_exts():
            seen.setdefault((it.stem.lower(), e), []).append(it)
    for clashing in seen.values():
        if len(clashing) > 1:
            for it in clashing:
                if not it.renamed:
                    it.stem = f'{it.stem} [{short_hash(it.file.id)}]'
                    it.renamed = True
    items.extend(folder_items)

    for sub in folder.dataFolders:
        if sub.name.lower() in [s.lower() for s in SKIP_FOLDERS]:
            skipped_folders.append(f'{project.name}/{rel_dir}/{sub.name}')
            continue
        collect(sub, rel_dir / sanitize(sub.name), hub, project, items, skipped_folders)


def inventory():
    items, skipped = [], []
    hubs = list(app.data.dataHubs)
    for hub in hubs:
        app.data.activeHub = hub
        hub_dir = Path(sanitize(hub.name)) if len(hubs) > 1 else Path()
        for project in app.data.dataProjects:
            if project.name.lower() in [s.lower() for s in SKIP_PROJECTS]:
                skipped.append(project.name)
                continue
            log(f'Inventaris: {hub.name} / {project.name}')
            collect(project.rootFolder, hub_dir / sanitize(project.name), hub, project, items, skipped)
            adsk.doEvents()
    return items, skipped


def count_bodies(design: adsk.fusion.Design) -> int:
    root = design.rootComponent
    n = root.bRepBodies.count
    for occ in root.allOccurrences:
        n += occ.component.bRepBodies.count
    return n


def unhide(component):
    for attr in ('isBodiesFolderLightBulbOn',):
        try:
            if not getattr(component, attr):
                setattr(component, attr, True)
        except Exception:
            pass
    for body in component.bRepBodies:
        try:
            if not body.isLightBulbOn:
                body.isLightBulbOn = True
        except Exception:
            pass
    for occ in component.occurrences:
        try:
            if not occ.isLightBulbOn:
                occ.isLightBulbOn = True
        except Exception:
            pass
        unhide(occ.component)


def export_design(item: Item):
    f3d = path_with(item, 'f3d')
    f3z = path_with(item, 'f3z')
    step = path_with(item, 'step')
    have_archive = nonempty(f3d) or nonempty(f3z)
    need_archive = EXPORT_F3D and not have_archive
    need_step = EXPORT_STEP and not nonempty(step)
    if not need_archive and not need_step:
        return 'al aanwezig', ''

    notes = []
    doc = app.documents.open(item.file, True)
    try:
        doc.activate()
        design = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
        em = design.exportManager
        f3d.parent.mkdir(parents=True, exist_ok=True)

        if need_archive:
            has_refs = doc.documentReferences.count > 0
            target = f3z if has_refs else f3d
            em.execute(em.createFusionArchiveExportOptions(str(target)))
            if not nonempty(target):
                raise Exception(f'archief niet aangemaakt: {target}')
            set_mtime(target, item.file)
            notes.append(target.suffix)

        if need_step:
            if count_bodies(design) == 0:
                notes.append('geen solid bodies, geen STEP')
            else:
                if UNHIDE_ALL_FOR_STEP:
                    unhide(design.rootComponent)
                em.execute(em.createSTEPExportOptions(str(step)))
                if not nonempty(step):
                    raise Exception(f'STEP niet aangemaakt: {step}')
                set_mtime(step, item.file)
                notes.append('.step')
    finally:
        doc.close(False)
    return 'geexporteerd', ', '.join(notes)


def export_drawing(item: Item):
    pdf = path_with(item, 'pdf')
    if nonempty(pdf):
        return 'al aanwezig', ''
    doc = app.documents.open(item.file, True)
    try:
        doc.activate()
        drawing = adsk.drawing.Drawing.cast(app.activeProduct)
        pdf.parent.mkdir(parents=True, exist_ok=True)
        em = drawing.exportManager
        em.execute(em.createPDFExportOptions(str(pdf)))
        if not nonempty(pdf):
            raise Exception(f'PDF niet aangemaakt: {pdf}')
        set_mtime(pdf, item.file)
    finally:
        doc.close(False)
    return 'geexporteerd', '.pdf'


def download_other(item: Item):
    target = item.other_path()
    if nonempty(target):
        return 'al aanwezig', ''
    target.parent.mkdir(parents=True, exist_ok=True)
    item.file.download(str(target), None)
    if not nonempty(target):
        # sommige typen komen met een andere naam/extensie binnen
        matches = [p for p in target.parent.glob(item.stem + '*') if p.is_file()]
        if not matches:
            raise Exception(f'download leverde geen bestand op: {target}')
        return 'gedownload', ', '.join(p.name for p in matches)
    set_mtime(target, item.file)
    return 'gedownload', target.suffix


def process(item: Item):
    if item.kind == 'design':
        return export_design(item)
    if item.kind == 'drawing':
        if not EXPORT_PDF:
            return 'overgeslagen', 'PDF uit'
        return export_drawing(item)
    if not DOWNLOAD_OTHER:
        return 'overgeslagen', 'download uit'
    return download_other(item)


def run(context):
    global log_fh, report_fh, report
    try:
        EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y-%m-%d_%H%M')
        log_fh = open(EXPORT_ROOT / f'_backup_log_{stamp}.txt', 'w', encoding='utf-8')

        progress = ui.createProgressDialog()
        progress.isCancelButtonShown = True
        progress.show('Fusion backup', 'Bestanden in de cloud inventariseren...', 0, 1, 0)
        adsk.doEvents()
        original_hub = app.data.activeHub
        items, skipped = inventory()
        progress.hide()

        by_ext = {}
        for it in items:
            by_ext[it.ext] = by_ext.get(it.ext, 0) + 1
        summary = ', '.join(f'{n}x .{e}' for e, n in sorted(by_ext.items()))
        msg = (f'{len(items)} bestanden gevonden ({summary}).\n'
               f'Overgeslagen projecten/mappen: {len(skipped)}\n\n'
               f'Export naar {EXPORT_ROOT}\n'
               f'Fusion is tijdens de export niet bruikbaar. Starten?')
        if ui.messageBox(msg, 'Fusion backup', adsk.core.MessageBoxButtonTypes.OKCancelButtonType) \
                != adsk.core.DialogResults.DialogOK:
            return

        report_fh = open(EXPORT_ROOT / f'_backup_rapport_{stamp}.csv', 'w', newline='', encoding='utf-8-sig')
        report = csv.writer(report_fh, delimiter=';')
        report.writerow(['hub', 'project', 'map', 'naam', 'type', 'versie', 'status', 'uitvoer', 'fout'])
        for s in skipped:
            report.writerow(['', s, '', '', '', '', 'overgeslagen (instelling)', '', ''])

        counts = {}
        progress.show('Fusion backup', '%v van %m', 0, len(items), 0)
        for i, item in enumerate(items):
            if progress.wasCancelled:
                log('Geannuleerd door gebruiker')
                break
            progress.message = f'{i + 1} van {len(items)}: {item.project.name} / {item.file.name}'
            progress.progressValue = i
            adsk.doEvents()
            if app.data.activeHub.id != item.hub.id:
                app.data.activeHub = item.hub
            error = ''
            try:
                status, out = process(item)
            except Exception:
                status, out = 'FOUT', ''
                error = traceback.format_exc().strip().splitlines()[-1]
                log(f'FOUT bij {item.rel_dir / item.file.name}\n{traceback.format_exc()}')
            counts[status] = counts.get(status, 0) + 1
            log(f'{status}: {item.rel_dir / item.file.name} {out}')
            report.writerow([item.hub.name, item.project.name, str(item.rel_dir), item.file.name,
                             item.ext, item.file.versionNumber, status, out, error])
            report_fh.flush()
        progress.hide()

        try:
            app.data.activeHub = original_hub
        except Exception:
            pass

        result = '\n'.join(f'{k}: {v}' for k, v in sorted(counts.items()))
        log(result)
        ui.messageBox(f'Klaar.\n\n{result}\n\nRapport en log staan in {EXPORT_ROOT}')
    except Exception:
        tb = traceback.format_exc()
        if log_fh:
            log(tb)
        ui.messageBox(f'Backup gestopt met een fout:\n{tb}')
    finally:
        if report_fh:
            report_fh.close()
        if log_fh:
            log_fh.close()
