import assert from 'node:assert/strict';
export function harness() {
  const document = {activeElement:null, createElement:tag => new Node(tag),createTextNode:text=>{const node=new Node('#text');node.textContent=text;return node;}};
  class Node {
    constructor(tag) { this.tagName=tag; this.children=[]; this.listeners=new Map(); this.attrs={}; this.style={}; this._text=''; this.value=''; this.disabled=false; this.ownerDocument=document; }
    set textContent(value) { this._text=String(value); this.children=[]; }
    get textContent() { return this._text+this.children.map(child=>child.textContent).join(''); }
    set innerHTML(_) { throw new Error('innerHTML 금지'); }
    set outerHTML(_) { throw new Error('outerHTML 금지'); }
    insertAdjacentHTML() { throw new Error('insertAdjacentHTML 금지'); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { if(this.contains(document.activeElement))document.activeElement=null; this._text='';this.children=children; }
    setAttribute(key,value) { assert.ok(!/^on/i.test(key)); this.attrs[key]=String(value); }
    querySelectorAll(selector) { return this.children.flatMap(child=>[child,...child.querySelectorAll('*')]).filter(node=>selector==='*'||selector.split(',').some(part=>{const attrs=[...part.matchAll(/\[([^=\]]+)(?:=["']?([^"'\]]+)["']?)?\]/g)];const tag=part.match(/^[a-z]+/)?.[0];return (!tag||node.tagName===tag)&&attrs.every(([,key,value])=>node.getAttribute(key)!==null&&(value===undefined||node.getAttribute(key)===value));})); }
    querySelector(selector) {return this.querySelectorAll(selector)[0]||null;}
    get lastChild(){return this.children.at(-1);}
    getAttribute(key) { return this.attrs[key]??null; }
    addEventListener(type,fn) { if(!this.listeners.has(type))this.listeners.set(type,new Set());this.listeners.get(type).add(fn); }
    removeEventListener(type,fn) { this.listeners.get(type)?.delete(fn); }
    contains(target) { return this===target||this.children.some(child=>child.contains(target)); }
    focus() { document.activeElement=this; }
    async fire(type,extra={}) { if(this.disabled)return; const event={target:this,preventDefault(){this.defaultPrevented=true;},...extra};for(const fn of this.listeners.get(type)||[])await fn(event);return event; }
  }
  return {document};
}
export const all=node=>[node,...node.children.flatMap(all)];
export const action=(root,name)=>all(root).find(node=>node.getAttribute('data-execution-action')===name);
export const field=(root,name)=>all(root).find(node=>node.name===name);
