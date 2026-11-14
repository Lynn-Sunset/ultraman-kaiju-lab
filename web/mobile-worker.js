import {createMobileModel} from './mobile-model.js';
let predict;
self.onmessage=async ({data})=>{
  try {
    if(data.type==='load'){
      const config=data.config;
      const specResponse=await fetch(new URL('./data/mobile-graph.json',import.meta.url));
      if(!specResponse.ok) throw Error('errorModelDownload');
      const spec=await specResponse.json();
      if(spec.sha256!==config.sha256) throw Error('errorChecksum');
      const parts=config.mobileParts || [config.modelFile];
      let received=0;
      const chunks=[];
      for(const path of parts){
        let chunk;
        for(let attempt=0;attempt<3;attempt++){
          const controller=new AbortController();
          const timer=setTimeout(()=>controller.abort(),25000);
          try{
            const r=await fetch(new URL(path,import.meta.url),{signal:controller.signal});
            if(!r.ok)throw Error('errorModelDownload');
            chunk=await r.arrayBuffer();break;
          }catch{if(attempt===2)throw Error('errorModelDownload');}
          finally{clearTimeout(timer);}
        }
        chunks.push(chunk);received+=chunk.byteLength;
        self.postMessage({id:data.id,progress:{mb:received/1048576}});
      }
      const bytes=await new Blob(chunks).arrayBuffer();
      const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',bytes));
      if(Array.from(digest,v=>v.toString(16).padStart(2,'0')).join('')!==spec.sha256)throw Error('errorChecksum');
      predict=createMobileModel(spec,bytes);
      self.postMessage({id:data.id,ready:true});
    }else{
      const logits=predict(data.input);
      self.postMessage({id:data.id,logits},[logits.buffer]);
    }
  }catch(error){self.postMessage({id:data.id,error:error.message});}
};
