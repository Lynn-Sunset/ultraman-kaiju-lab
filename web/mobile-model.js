// Inference for the fixed NCHW MobileNet graph exported by scripts/export-mobile.py.
export function createMobileModel(spec, bytes) {
  const weights = new Map(Object.entries(spec.weights).map(([name, [offset, dims]]) => {
    const length = dims.reduce((a,b) => a*b, 1);
    return [name, { data: new Float32Array(bytes.slice(offset, offset + length*4)), dims }];
  }));
  return input => {
    const values = new Map(weights);
    values.set('image', {data: input, dims: [3,224,224]});
    for (const [op, names, dest, attrs] of spec.graph) {
      const [x,w,b] = names.map(name => values.get(name));
      let dims = x.dims, out;
      const [channels,h,width] = dims;
      const plane = h*width;
      if (op === 'Conv') {
        const [oc,ic,kh,kw] = w.dims;
        const pad = attrs.pads[0], stride = attrs.strides[0];
        const oh = Math.floor((h+2*pad-kh)/stride)+1, ow = Math.floor((width+2*pad-kw)/stride)+1;
        dims = [oc,oh,ow]; out = new Float32Array(oc*oh*ow);
        for(let c=0;c<oc;c++){
          const start = Math.floor(c/(oc/attrs.group))*ic, base=c*oh*ow;
          out.fill(b.data[c],base,base+oh*ow);
          for(let i=0;i<ic;i++) for(let ky=0;ky<kh;ky++) for(let kx=0;kx<kw;kx++){
            const coef=w.data[((c*ic+i)*kh+ky)*kw+kx];
            const xmin=Math.max(0,Math.ceil((pad-kx)/stride)), xmax=Math.min(ow,Math.ceil((width+pad-kx)/stride));
            for(let y=0;y<oh;y++){
              const sy=y*stride+ky-pad;
              if(sy<0 || sy>=h) continue;
              let src=(start+i)*plane+sy*width+xmin*stride+kx-pad;
              for(let j=xmin;j<xmax;j++,src+=stride) out[base+y*ow+j]+=x.data[src]*coef;
            }
          }
        }
      } else if(op==='GlobalAveragePool'){
        dims=[channels,1,1]; out=new Float32Array(channels);
        for(let c=0;c<channels;c++){let sum=0;for(let i=0;i<plane;i++)sum+=x.data[c*plane+i];out[c]=sum/plane;}
      } else if(op==='Flatten'){out=x.data;dims=[out.length];}
      else if(op==='Gemm'){
        dims=[w.dims[0]];out=new Float32Array(dims[0]);
        for(let j=0;j<out.length;j++){let sum=b.data[j];for(let i=0;i<x.data.length;i++)sum+=x.data[i]*w.data[j*x.data.length+i];out[j]=sum;}
      } else if(op==='Mul'){
        const full=x.data.length>=w.data.length?x:w, scale=full===x?w:x;
        dims=full.dims;const block=full.data.length/scale.data.length;
        out=full.data.map((v,i)=>v*scale.data[Math.floor(i/block)]);
      } else if(op==='Add') out=x.data.map((v,i)=>v+w.data[i]);
      else if(op==='Relu') out=x.data.map(v=>Math.max(0,v));
      else if(op==='HardSwish') out=x.data.map(v=>v*Math.max(0,Math.min(1,v/6+0.5)));
      else if(op==='HardSigmoid') out=x.data.map(v=>Math.max(0,Math.min(1,v*attrs.alpha+0.5)));
      else throw Error('errorModel');
      values.set(dest,{data:out,dims});
    }
    return values.get('logits').data;
  };
}
