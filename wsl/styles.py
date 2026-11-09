# styles.py - Full-bleed edge-to-edge CSS and Print JS helper

STUDIO_CSS = """
/* Eliminate outer dead space on left/right/top */
body, .gradio-container {
    max-width: 100vw !important;
    width: 100vw !important;
    margin: 0 !important;
    padding: 2px 6px !important;
    overflow-x: hidden !important;
}
footer { display: none !important; }

/* Prevent the 3-column workspace from wrapping the right panel to the bottom */
.workspace-row {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    align-items: flex-start !important;
    gap: 8px !important;
    width: 100% !important;
}

/* Slimmer borders & tighter internal padding */
.block, .form, .tabitem {
    border-width: 1px !important;
    padding: 6px !important;
    border-radius: 6px !important;
    box-shadow: none !important;
}
.gap { gap: 6px !important; }

/* Independent scrolling for left and right sidebars */
.left-col {
    flex: 0 0 230px !important;
    max-width: 230px !important;
    max-height: 91vh;
    overflow-y: auto;
}
.center-col {
    flex: 1 1 auto !important;
    min-width: 320px !important;
}
.right-col {
    flex: 0 0 330px !important;
    max-width: 330px !important;
    max-height: 91vh;
    overflow-y: auto;
    padding-right: 4px !important;
}
"""

# JavaScript to open the generated A4 sheet in a clean zero-margin print preview window
PRINT_A4_JS = """
() => {
    const container = document.querySelector('#a4-preview-box');
    const img = container ? container.querySelector('img') : null;
    if (!img || !img.src) {
        alert('Please generate the A4 sheet preview first.');
        return;
    }
    const win = window.open('', '_blank');
    win.document.write(`
        <html>
        <head>
            <title>Print A4 Sheet</title>
            <style>
                @page { size: A4 portrait; margin: 0; }
                body { margin: 0; display: flex; justify-content: center; align-items: center; background: #fff; }
                img { width: 210mm; height: 297mm; object-fit: contain; }
            </style>
        </head>
        <body>
            <img src="${img.src}" onload="setTimeout(() => { window.print(); }, 250);" />
        </body>
        </html>
    `);
    win.document.close();
}
"""