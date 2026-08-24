document.addEventListener('DOMContentLoaded',()=>{
  const root=document.querySelector('[data-default-journal]');
  if(!root)return;

  const curated=document.querySelector('.curated-journal');
  if(curated)curated.hidden=true;

  const pages=[...root.querySelectorAll('.default-journal-book>[data-default-page]')];
  const prev=root.querySelector('[data-default-prev]');
  const next=root.querySelector('[data-default-next]');
  const indicator=root.querySelector('[data-default-indicator]');
  if(!pages.length||!prev||!next||!indicator)return;

  let current=0;
  let animating=false;

  const sync=()=>{
    pages.forEach((sheet,index)=>{
      sheet.classList.toggle('active',index===current);
      sheet.classList.toggle('turned',index<current);
      sheet.style.zIndex=index<current?String(index+1):String(100-index);
    });
    indicator.textContent=`PAGE ${String(current+1).padStart(2,'0')} / ${String(pages.length).padStart(2,'0')}`;
    prev.disabled=current===0||animating;
    next.disabled=current===pages.length-1||animating;
  };

  const finish=sheet=>{
    sheet.classList.remove('flip-live');
    animating=false;
    sync();
  };

  next.addEventListener('click',()=>{
    if(animating||current>=pages.length-1)return;
    animating=true;
    const leaving=pages[current];
    const entering=pages[current+1];
    leaving.style.zIndex='120';
    entering.style.zIndex='110';
    leaving.classList.add('flip-live');
    prev.disabled=next.disabled=true;
    requestAnimationFrame(()=>requestAnimationFrame(()=>leaving.classList.add('turned')));
    current+=1;
    indicator.textContent=`PAGE ${String(current+1).padStart(2,'0')} / ${String(pages.length).padStart(2,'0')}`;
    setTimeout(()=>finish(leaving),940);
  });

  prev.addEventListener('click',()=>{
    if(animating||current<=0)return;
    animating=true;
    const returning=pages[current-1];
    const leaving=pages[current];
    returning.style.zIndex='120';
    leaving.style.zIndex='110';
    returning.classList.add('flip-live');
    prev.disabled=next.disabled=true;
    requestAnimationFrame(()=>requestAnimationFrame(()=>returning.classList.remove('turned')));
    current-=1;
    indicator.textContent=`PAGE ${String(current+1).padStart(2,'0')} / ${String(pages.length).padStart(2,'0')}`;
    setTimeout(()=>finish(returning),940);
  });

  sync();
});
