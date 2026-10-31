/* Mobile Clinic — Core Vanilla JS */
(function () {
  "use strict";

  // Header scroll
  const header = document.querySelector(".site-header");
  if (header) {
    window.addEventListener("scroll", () => {
      header.classList.toggle("scrolled", window.scrollY > 20);
    }, { passive: true });
  }

  // Mobile nav
  const toggle = document.querySelector(".mobile-toggle");
  const mobileNav = document.querySelector(".mobile-nav");
  const closeNav = document.querySelector(".mobile-nav-close");
  if (toggle && mobileNav) {
    toggle.addEventListener("click", () => mobileNav.classList.add("open"));
    closeNav?.addEventListener("click", () => mobileNav.classList.remove("open"));
    mobileNav.addEventListener("click", (e) => {
      if (e.target === mobileNav) mobileNav.classList.remove("open");
    });
  }

  // Auto-dismiss flashes
  document.querySelectorAll(".flash-messages .alert").forEach((el) => {
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateX(40px)";
      setTimeout(() => el.remove(), 300);
    }, 5000);
  });

  // Scroll reveal
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const reveals = document.querySelectorAll(".reveal");
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          e.target.classList.add("revealed");
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.12 });
    reveals.forEach((el) => io.observe(el));
  }

  // Image preview for file inputs
  document.querySelectorAll("[data-image-preview]").forEach((input) => {
    input.addEventListener("change", function () {
      const preview = document.querySelector(this.dataset.imagePreview);
      if (!preview || !this.files?.length) return;
      preview.innerHTML = "";
      Array.from(this.files).forEach((file) => {
        if (!file.type.startsWith("image/")) return;
        const img = document.createElement("img");
        img.src = URL.createObjectURL(file);
        img.style.cssText = "width:80px;height:80px;object-fit:cover;border-radius:8px;margin:4px;";
        preview.appendChild(img);
      });
    });
  });

  // Confirm dialogs
  document.querySelectorAll("[data-confirm]").forEach((el) => {
    el.addEventListener("click", (e) => {
      if (!confirm(el.dataset.confirm)) e.preventDefault();
    });
  });

  // Countdown timers
  document.querySelectorAll("[data-countdown]").forEach((el) => {
    const end = new Date(el.dataset.countdown).getTime();
    const tick = () => {
      const diff = end - Date.now();
      if (diff <= 0) {
        el.textContent = "Expired";
        return;
      }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      el.textContent = `${h}h ${m}m ${s}s`;
      requestAnimationFrame(() => setTimeout(tick, 1000));
    };
    tick();
  });
})();

(function(){
  var loader=document.getElementById('page-loader');
  if(!loader)return;
  function show(){loader.classList.add('active');loader.setAttribute('aria-hidden','false');}
  function hide(){loader.classList.remove('active');loader.setAttribute('aria-hidden','true');}
  window.addEventListener('beforeunload',show);
  document.addEventListener('submit',function(e){
    var f=e.target;
    if(f && f.tagName==='FORM' && !f.hasAttribute('data-no-loader')) show();
  },true);
  document.addEventListener('click',function(e){
    var a=e.target.closest && e.target.closest('a[href]');
    if(!a)return;
    var href=a.getAttribute('href')||'';
    if(href.startsWith('#')||href.startsWith('javascript:')||a.target==='_blank'||a.hasAttribute('download'))return;
    if(href.startsWith('http') && href.indexOf(location.host)===-1)return;
    show();
  },true);
  window.addEventListener('pageshow',hide);
  document.addEventListener('DOMContentLoaded',hide);
})();

