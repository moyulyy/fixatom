/* Local-only 3Dmol renderer. Python owns all constraint state. */
'use strict';
let viewer, bridge, model, structure = null, generation = 0;
let mode = 'rotate', style = 'ball', showCell = true, masks = [];
let appearance = {};
let cameraState = {projection: 'orthographic', fov: 45, depthCue: false, depthIntensity: 35};

function applyCamera(settings) {
    cameraState = {...settings};
    viewer.setCameraParameters({fov: settings.fov});
    viewer.setProjection(settings.projection);
    const intensity = settings.depthIntensity / 100;
    viewer.enableFog(settings.depthCue && intensity > 0 ? {fogStart: .95 - .85 * intensity, fogEnd: 1.2 - .2 * intensity} : false);
    document.getElementById('projection-note').textContent =
        (settings.projection === 'orthographic' ? '正交投影' : `透视投影 · ${settings.fov}°`) +
        (settings.depthCue ? ` · 深度雾化 ${settings.depthIntensity}%` : '');
}
const layer = document.getElementById('selection-layer');
const rectangle = document.getElementById('selection');
const hint = document.getElementById('hint');
let drag = null;

function reportError(message) {
    hint.textContent = '渲染错误：' + message;
    if (bridge) bridge.reportError(String(message));
}
window.addEventListener('error', event => reportError(event.message));

function atomStyle(atom) {
    const settings = appearance[atom.elem] || {color: '#a0a9b8', diameter: .86};
    const sphere = {radius: settings.diameter / 2, color: settings.color};
    if (style === 'space') return {sphere};
    if (style === 'line') return {line: {linewidth: 1.5, color: settings.color}, sphere};
    return {sphere, stick: {radius: 0.12, color: settings.color}};
}
function meshRadius(atom) {
    return atomStyle(atom).sphere.radius * 1.12;
}
function updateLegend() {
    const legend = document.getElementById('legend');
    const entries = document.getElementById('legend-entries');
    entries.replaceChildren();
    if (!structure) { legend.hidden = true; return; }
    legend.hidden = false;
    const counts = new Map();
    for (const atom of structure.atoms) counts.set(atom.elem, (counts.get(atom.elem) || 0) + 1);
    for (const [element, count] of counts) {
        const settings = appearance[element];
        if (!settings) continue;
        const row = document.createElement('div');
        row.className = 'legend-row';
        const ball = document.createElement('span');
        ball.className = 'legend-ball';
        ball.style.backgroundColor = settings.color;
        const name = document.createElement('strong');
        name.textContent = element;
        const detail = document.createElement('span');
        detail.className = 'legend-detail';
        detail.textContent = `Ø ${Number(settings.diameter.toFixed(3))} Å · ${count}`;
        row.append(ball, name, detail);
        entries.append(row);
    }
}
function clicked(index) {
    if (mode === 'point' && bridge) bridge.selectAtoms(JSON.stringify({generation, indices: [index], action: 'toggle'}));
}
function applyStandardView(request) {
    if (!model || !structure || !structure.validCell || request.generation !== generation) return;
    cancelDrag();
    // getView uses [center.x, center.y, center.z, zoom, q.x, q.y, q.z, q.w].
    // Rotate the displayed model only; the ASE coordinates remain untouched.
    viewer.zoomTo();
    const view = viewer.getView();
    view.splice(4, 4, ...request.quaternion);
    view[8] = 0;
    view[9] = 0;
    viewer.setView(view);
    viewer.render();
}
function drawCell() {
    if (!showCell || !structure.validCell) return;
    const c = structure.cell;
    const corners = Array.from({length: 8}, (_, n) => ({
        x: ((n & 1) ? c[0][0] : 0) + ((n & 2) ? c[1][0] : 0) + ((n & 4) ? c[2][0] : 0),
        y: ((n & 1) ? c[0][1] : 0) + ((n & 2) ? c[1][1] : 0) + ((n & 4) ? c[2][1] : 0),
        z: ((n & 1) ? c[0][2] : 0) + ((n & 2) ? c[1][2] : 0) + ((n & 4) ? c[2][2] : 0)
    }));
    for (let i = 0; i < 8; i++) for (const bit of [1, 2, 4]) {
        if (!(i & bit)) viewer.addLine({start: corners[i], end: corners[i | bit], color: '#a7b5c8', linewidth: 1});
    }
}
function renderStyle() {
    if (!model) return;
    viewer.removeAllShapes();
    // Apply shared styles in groups to avoid a full atom scan for every atom.
    const groups = new Map();
    for (const atom of structure.atoms) {
        if (!groups.has(atom.elem)) groups.set(atom.elem, []);
        groups.get(atom.elem).push(atom.index);
    }
    for (const [elem, indices] of groups) model.setStyle({index: indices}, atomStyle({elem}));
    for (const atom of structure.atoms) {
        const mask = masks[atom.index] || [false, false, false];
        const locked = mask.every(Boolean), partial = !locked && mask.some(Boolean);
        if (locked || partial) {
            viewer.addSphere({center: atom, radius: meshRadius(atom),
                color: locked ? '#111111' : '#cf861d', wireframe: true, linewidth: 1,
                quality: 1, clickable: true, callback: () => clicked(atom.index)});
        }
    }
    model.setClickable({}, true, atom => clicked(atom.index));
    drawCell();
    viewer.render();
    updateLegend();
}
function applyState(state) {
    try {
        const cameraChanged = state.camera && JSON.stringify(state.camera) !== JSON.stringify(cameraState);
        const redraw = !!state.structure ||
            (state.masks && JSON.stringify(state.masks) !== JSON.stringify(masks)) ||
            (state.style && state.style !== style) ||
            (state.appearance && JSON.stringify(state.appearance) !== JSON.stringify(appearance)) ||
            (state.showCell !== undefined && state.showCell !== showCell);
        if (state.structure) {
            generation = state.generation;
            structure = state.structure;
            viewer.clear();
            viewer.setView([0, 0, 0, 0, 0, 0, 0, 1, 0, 0]);
            model = viewer.addModel();
            model.addAtoms(structure.atoms);
            document.getElementById('empty').style.display = 'none';
        }
        if (state.masks) masks = state.masks;
        if (state.appearance) appearance = state.appearance;
        if (state.style) style = state.style;
        if (state.showCell !== undefined) showCell = state.showCell;
        if (state.mode) setMode(state.mode);
        if (state.camera && (cameraChanged || state.structure)) applyCamera(state.camera);
        if (redraw) renderStyle();
        else if (cameraChanged) viewer.render();
        if (state.structure) { viewer.zoomTo(); viewer.rotate(20, 'x'); viewer.rotate(-20, 'y'); viewer.render(); }
    } catch (error) { reportError(error.stack || error.message); }
}
function cancelDrag() { drag = null; rectangle.style.display = 'none'; }
function setMode(value) {
    mode = value;
    cancelDrag();
    layer.style.display = mode === 'box' ? 'block' : 'none';
    hint.textContent = mode === 'box' ? '拖动框选固定 · Shift + 拖动解除 · 穿透选择所有深度' :
        mode === 'point' ? '点击原子固定 / 解除固定 · 拖动仍可旋转' : '拖动旋转 · 滚轮缩放 · 右键拖动平移';
}
function indicesInRectangle(x1, y1, x2, y2) {
    if (!structure) return [];
    const [left, right] = [Math.min(x1, x2), Math.max(x1, x2)];
    const [top, bottom] = [Math.min(y1, y2), Math.max(y1, y2)];
    // modelToScreen returns document CSS pixels, matching PointerEvent.pageX/Y.
    return structure.atoms.filter(atom => {
        const p = viewer.modelToScreen(atom);
        return p.x >= left && p.x <= right && p.y >= top && p.y <= bottom;
    }).map(atom => atom.index);
}
layer.addEventListener('pointerdown', event => {
    if (event.button !== 0 || !structure) return;
    event.preventDefault();
    layer.setPointerCapture(event.pointerId);
    drag = {x: event.pageX, y: event.pageY, release: event.shiftKey};
    Object.assign(rectangle.style, {display: 'block', left: drag.x + 'px', top: drag.y + 'px', width: '0px', height: '0px'});
});
layer.addEventListener('pointermove', event => {
    if (!drag) return;
    Object.assign(rectangle.style, {left: Math.min(drag.x, event.pageX) + 'px', top: Math.min(drag.y, event.pageY) + 'px',
        width: Math.abs(drag.x - event.pageX) + 'px', height: Math.abs(drag.y - event.pageY) + 'px'});
});
layer.addEventListener('pointerup', event => {
    if (!drag) return;
    const indices = indicesInRectangle(drag.x, drag.y, event.pageX, event.pageY);
    if (bridge && Math.hypot(drag.x - event.pageX, drag.y - event.pageY) > 3)
        bridge.selectAtoms(JSON.stringify({generation, indices, action: drag.release ? 'release' : 'fix'}));
    cancelDrag();
});
layer.addEventListener('pointercancel', cancelDrag);
layer.addEventListener('lostpointercapture', cancelDrag);
window.addEventListener('blur', cancelDrag);
document.addEventListener('keydown', event => {
    const shortcuts = {'1': 'rotate', '2': 'point', '3': 'box', Escape: 'rotate'};
    if (shortcuts[event.key] && bridge) bridge.requestMode(shortcuts[event.key]);
});
window.addEventListener('resize', () => { if (viewer) { viewer.resize(); viewer.render(); } });

try {
    viewer = $3Dmol.createViewer(document.getElementById('viewer'), {backgroundColor: '#f8fafc', antialias: true});
    applyCamera(cameraState);
    if (typeof qt !== 'undefined') {
        new QWebChannel(qt.webChannelTransport, channel => {
            bridge = channel.objects.bridge;
            bridge.stateChanged.connect(json => applyState(JSON.parse(json)));
            bridge.viewRequested.connect(json => applyStandardView(JSON.parse(json)));
            bridge.command.connect(command => {
                if (command === 'reset' && model) { viewer.zoomTo(); viewer.render(); }
            });
            bridge.ready();
        });
    } else {
        hint.textContent = '请通过 app.py 打开此视图';
    }
} catch (error) { reportError(error.message); }
