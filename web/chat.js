'use strict';

const chatList = document.querySelector('#chat-list');
const thread = document.querySelector('#thread');
const welcome = document.querySelector('#welcome');
const scroll = document.querySelector('#scroll');
const composer = document.querySelector('#composer');
const input = document.querySelector('#message');
const send = document.querySelector('.send');
const status = document.querySelector('#status');
const toggle = document.querySelector('.sidebar-toggle');

const chats = [];
let active = newChat();

function newChat() {
  return {turns: [], draft: '', busy: false};
}

function hideSidebar() {
  document.body.classList.remove('sidebar-open');
  toggle.setAttribute('aria-expanded', 'false');
}

toggle.addEventListener('click', () => {
  toggle.setAttribute('aria-expanded', String(document.body.classList.toggle('sidebar-open')));
});

function selectChat(chat) {
  active = chat;
  input.value = chat.draft;
  hideSidebar();
  render();
  scroll.scrollTop = scroll.scrollHeight;
  input.focus();
}

document.querySelector('.new').addEventListener('click', () => selectChat(newChat()));

function renderSidebar() {
  chatList.replaceChildren();
  for (const chat of chats) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = chat.turns[0].prompt.replace(/\s+/g, ' ').slice(0, 46);
    if (chat === active) button.setAttribute('aria-current', 'true');
    button.addEventListener('click', () => selectChat(chat));
    chatList.append(button);
  }
}

function inline(node, text) {
  for (const part of text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g)) {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      const strong = document.createElement('strong');
      strong.textContent = part.slice(2, -2);
      node.append(strong);
    } else if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      const code = document.createElement('code');
      code.textContent = part.slice(1, -1);
      node.append(code);
    } else {
      node.append(part);
    }
  }
}

function formatReply(node, text) {
  let paragraph = null;
  let list = null;
  let code = null;
  for (const line of text.split('\n')) {
    if (line.startsWith('```')) {
      if (code) {
        code = null;
      } else {
        const pre = document.createElement('pre');
        code = document.createElement('code');
        pre.append(code);
        node.append(pre);
      }
      paragraph = list = null;
    } else if (code) {
      code.append(line + '\n');
    } else if (!line.trim()) {
      paragraph = list = null;
    } else {
      const item = line.match(/^\s*(\d+[.)]|[-*])\s+(.*)$/);
      if (item) {
        const tag = /^\d/.test(item[1]) ? 'ol' : 'ul';
        if (list?.localName !== tag) {
          list = document.createElement(tag);
          if (tag === 'ol') list.start = parseInt(item[1], 10);
          node.append(list);
        }
        const li = document.createElement('li');
        inline(li, item[2]);
        list.append(li);
        paragraph = null;
      } else {
        list = null;
        if (!paragraph) {
          paragraph = document.createElement('p');
          node.append(paragraph);
        } else {
          paragraph.append(document.createElement('br'));
        }
        inline(paragraph, line);
      }
    }
  }
}

function renderThread() {
  const nearBottom = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 80;
  const last = active.turns.at(-1);
  thread.hidden = !last;
  welcome.hidden = Boolean(last);
  thread.replaceChildren();
  for (const turn of active.turns) {
    const user = document.createElement('div');
    user.className = 'user';
    user.textContent = turn.prompt;
    const reply = document.createElement('article');
    reply.className = 'assistant';
    reply.setAttribute('aria-label', 'CsoulGPT reply');
    const text = turn.answer + (turn.stream ? (turn.answer ? '\n' : '') + turn.stream : '');
    if (active.busy && turn === last) {
      const streaming = document.createElement('p');
      streaming.className = 'streaming';
      streaming.textContent = text || '…';
      reply.append(streaming);
    } else {
      formatReply(reply, text);
      if (turn === last && (turn.truncated || turn.error)) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'message-action';
        button.textContent = turn.error ? 'Retry' : 'Continue';
        button.addEventListener('click', () => requestReply(active, turn));
        reply.append(button);
      }
    }
    thread.append(user, reply);
  }
  if (nearBottom) scroll.scrollTop = scroll.scrollHeight;
}

function syncComposer() {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight + 1, 150) + 'px';
  send.disabled = active.busy || !active.draft.trim();
  const last = active.turns.at(-1);
  status.textContent = active.busy ? 'CsoulGPT is replying…' :
    last?.error || (last?.truncated ? 'Reply reached the token limit.' : '');
}

function render() {
  renderSidebar();
  renderThread();
  syncComposer();
}

async function requestReply(chat, turn) {
  if (chat.busy) return;
  chat.busy = true;
  turn.error = '';
  turn.stream = '';
  render();
  scroll.scrollTop = scroll.scrollHeight;

  const history = chat.turns.slice(0, -1)
    .filter(item => item.answer && !item.truncated && !item.error)
    .flatMap(item => [
      {role: 'user', content: item.prompt},
      {role: 'assistant', content: item.answer},
    ]);
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({prompt: turn.prompt, history, partial: turn.answer || null}),
    });
    if (!response.ok || !response.body) throw new Error('Could not connect to CsoulGPT. Try again.');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finished = false;
    try {
      while (!finished) {
        const {value, done} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {stream: true});
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          const event = JSON.parse(line);
          if (event.error) throw new Error(event.error);
          if (event.done) {
            const segment = turn.stream.trim();
            if (!segment) throw new Error('Ollama returned an empty reply. Try again.');
            turn.answer = turn.answer ? turn.answer + '\n' + segment : segment;
            turn.truncated = Boolean(event.truncated);
            finished = true;
            break;
          }
          turn.stream += event.text;
        }
        if (active === chat && !finished) renderThread();
      }
    } finally {
      await reader.cancel().catch(() => {});
    }
    if (!finished) throw new Error('The reply was interrupted. Try again.');
  } catch (error) {
    turn.error = error.message === 'Failed to fetch' ? 'Could not connect to CsoulGPT. Try again.' : error.message;
  } finally {
    turn.stream = '';
    chat.busy = false;
    if (active === chat) {
      render();
      input.focus();
    }
  }
}

input.addEventListener('input', () => {
  active.draft = input.value;
  syncComposer();
});

input.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!send.disabled) composer.requestSubmit();
  }
});

composer.addEventListener('submit', event => {
  event.preventDefault();
  const prompt = active.draft.trim();
  if (!prompt || active.busy) return;
  if (!active.turns.length) chats.unshift(active);
  const turn = {prompt, answer: '', stream: '', truncated: false, error: ''};
  active.turns.push(turn);
  active.draft = input.value = '';
  requestReply(active, turn);
});

render();
