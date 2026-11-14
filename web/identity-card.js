export function identityText(result) {
  const monster = result.winner;
  const score = (result.ranking[0].score * 100).toFixed(1);
  return `${result.mode === 'demo' ? '【结果示例】\n' : ''}你是${monster.name}！\n${monster.title} · 类别得分 ${score}%\n能力：${monster.abilities.join('、')}\n${monster.description}\n\n仅供娱乐，不代表真实身份、性格或能力。\n怪兽研究所 · KAIJU LAB`;
}

export async function renderIdentityCard(result) {
  const monster = result.winner;
  const image = new Image();
  image.src = new URL(`./portraits/${monster.id}.jpg`, import.meta.url).href;
  await image.decode();
  await document.fonts.ready;
  const canvas = document.createElement('canvas'); canvas.width = 1000; canvas.height = 1320;
  const ctx = canvas.getContext('2d');
  const font = '"Microsoft YaHei", "PingFang SC", system-ui, sans-serif';
  ctx.fillStyle = '#fffdfb'; ctx.fillRect(0, 0, 1000, 1320);
  ctx.fillStyle = '#d92f3d'; ctx.fillRect(0, 0, 1000, 157);
  ctx.fillStyle = '#fff'; ctx.font = `700 35px ${font}`; ctx.fillText('✳ 怪兽研究所', 60, 76);
  ctx.font = `18px ${font}`; ctx.fillText(result.mode === 'demo' ? '结果示例 · 与上传照片无关' : '你的奥特怪兽身份卡', 60, 120);
  ctx.font = `700 35px ${font}`; ctx.textAlign = 'right'; ctx.fillText(`${(result.ranking[0].score * 100).toFixed(1)}%`, 940, 77);
  ctx.font = `17px ${font}`; ctx.fillText('类别得分', 940, 116); ctx.textAlign = 'left';
  ctx.fillStyle = '#fff0ef'; ctx.fillRect(60, 200, 880, 460);
  const scale = Math.min(810 / image.naturalWidth, 425 / image.naturalHeight);
  ctx.globalCompositeOperation = 'multiply';
  ctx.drawImage(image, (1000 - image.naturalWidth * scale) / 2, 216 + (425 - image.naturalHeight * scale) / 2, image.naturalWidth * scale, image.naturalHeight * scale);
  ctx.globalCompositeOperation = 'source-over';
  ctx.fillStyle = '#d92f3d'; ctx.font = `700 59px ${font}`; ctx.fillText(`你是${monster.name}`, 60, 759);
  ctx.fillStyle = '#897779'; ctx.font = `22px ${font}`; ctx.fillText(`${monster.en} / ${monster.title}`, 60, 810);
  ctx.font = `22px ${font}`;
  let x = 60;
  for (const ability of monster.abilities) {
    const width = ctx.measureText(ability).width + 32;
    ctx.fillStyle = '#fff0ef'; ctx.fillRect(x, 852, width, 45);
    ctx.fillStyle = '#b34049'; ctx.fillText(ability, x + 16, 883); x += width + 13;
  }
  ctx.font = `25px ${font}`; ctx.fillStyle = '#67575a';
  let line = '', y = 962;
  for (const character of monster.description) {
    if (ctx.measureText(line + character).width > 880) { ctx.fillText(line, 60, y); y += 40; line = character; }
    else line += character;
  }
  if (line) ctx.fillText(line, 60, y);
  ctx.strokeStyle = '#eddfdc'; ctx.beginPath(); ctx.moveTo(60, 1200); ctx.lineTo(940, 1200); ctx.stroke();
  ctx.fillStyle = '#897779'; ctx.font = `18px ${font}`;
  ctx.fillText(result.mode === 'demo' ? '结果示例，与上传照片无关。' : '仅供娱乐，不代表真实身份、性格或能力。', 60, 1243);
  ctx.font = `16px ${font}`; ctx.fillText('非官方同人实验 · 角色及图片版权归原权利人所有', 60, 1281);
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
  if (!blob) throw new Error('身份卡生成失败，请重试。');
  return blob;
}
