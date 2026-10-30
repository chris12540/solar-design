// Search/acquire only after explicit clicks. Current editor stays open unchanged.
export function installAddressLookup() {
  const dialog=document.querySelector('#address-dialog'),form=dialog.querySelector('form');
  const input=dialog.querySelector('input'),message=dialog.querySelector('[role="status"]'),results=dialog.querySelector('.address-results');
  document.querySelector('#google-preview').onclick=()=>{dialog.showModal();input.focus()};
  dialog.querySelector('.address-close').onclick=()=>dialog.close();
  const post=async(path,data)=>{
    const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const result=await response.json();
    if(!response.ok||result.ok===false){
      if(result.reasons?.includes('API_KEY_IP_ADDRESS_BLOCKED'))throw new Error('Google blocked this machine’s outbound IP. Update API key’s allowed IP list.');
      if(result.httpStatus===404)throw new Error('Google has no Solar imagery at this address at the requested quality.');
      throw new Error(result.error||'Address/imagery request failed. Check server API configuration and coverage.');
    }
    return result;
  };
  let busy=false;
  form.onsubmit=async event=>{
    event.preventDefault();if(busy)return;busy=true;
    const submit=form.querySelector('button[type="submit"]');submit.disabled=true;results.replaceChildren();message.textContent='Searching…';
    try{
      const data=await post('/address-search',{query:input.value.trim()});
      message.textContent=data.results.length?'Select the property to load its imagery.':'No matching local property record. Check address or choose a property in loaded Phoenix-area data.';
      for(const item of data.results){
        const row=document.createElement('div'),label=document.createElement('span'),load=document.createElement('button');row.className='address-result';
        label.textContent=item.address;load.type='button';load.textContent='Load imagery';
        load.onclick=async()=>{
          if(busy)return;busy=true;
          for(const button of results.querySelectorAll('button'))button.disabled=true;
          submit.disabled=true;message.textContent='Loading imagery… Keep this window open.';
          try{
            const acquired=await post('/address-imagery',{token:item.token});
            const link=document.createElement('a');link.href='/?google='+encodeURIComponent(acquired.source);link.target='_blank';link.rel='noopener';link.textContent='Open image editor';
            load.replaceWith(link);link.focus();
            message.textContent='Imagery ready. Open image editor in a separate tab. Edits there are temporary.';
          }catch(error){message.textContent=error.message}
          finally{busy=false;submit.disabled=false;for(const button of results.querySelectorAll('button'))button.disabled=false}
        };
        row.append(label,load);results.append(row);
      }
    }catch(error){message.textContent=error.message}
    finally{busy=false;submit.disabled=false}
  };
}
