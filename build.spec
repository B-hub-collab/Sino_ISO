# -*- mode: python ; coding: utf-8 -*-

"""
PyInstaller 打包設定檔
使用方式: pyinstaller build.spec
"""

block_cipher = None

a = Analysis(
    ['main_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.template.json', '.'),
        ('core/*.py', 'core'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.scrolledtext',
        'pdfplumber',
        'neo4j',
        'openai',
        'numpy',
        'fitz',  # PyMuPDF
        'docx',  # python-docx
        'docx.shared',
        'docx.enum.text',
        'docx.enum.table',
        'docx.oxml',
        'docx.oxml.ns',
        're',
        'json',
        'pathlib',
        'datetime',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='契約檢查系統',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 不顯示命令列視窗
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 如果有圖示檔案，可以指定路徑
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='契約檢查系統',
)
