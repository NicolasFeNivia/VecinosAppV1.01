// Cliente WebSocket con reconexión. Uso: conectarWS(ruta, funcionAlMensaje)
function conectarWS(ruta, alMensaje) {
  const protocolo = location.protocol === 'https:' ? 'wss' : 'ws';
  let espera = 500;
  function abrir() {
    const ws = new WebSocket(`${protocolo}://${location.host}${ruta}`);
    ws.onopen = () => { espera = 500; };
    ws.onmessage = (e) => alMensaje(JSON.parse(e.data));
    ws.onclose = (e) => { if (e.code !== 4403) setTimeout(abrir, espera = Math.min(espera * 2, 10000)); };
  }
  abrir();
}
function avisar(titulo, cuerpo) {
  if ('Notification' in window && Notification.permission === 'granted') new Notification(titulo, { body: cuerpo });
}
