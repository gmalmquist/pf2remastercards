function generateCards() {
  const names = Array.from(new Set(Array.from(document.getElementsByClassName('spellnames'))
    .map(e => e.value)[0]
    .trim()
    .split("\n")
    .map(e => e.trim().toLocaleLowerCase())
    .filter(e => e.length > 0)));
  names.sort();
  document.write('Loading, this may take several seconds ...')
  fetch('/', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(names),
  }).then(x => x.text()).then(x => {
    document.open()
    document.write(x)
  });
}

