// A seat map puts each seat's tooltip in a hidden .seat-tooltip right after the seat,
// or after the link around it.
function seatTooltip(seat) {
  var next = (seat.parentElement && seat.parentElement.tagName === 'A' ? seat.parentElement : seat).nextElementSibling;
  return next && next.classList.contains('seat-tooltip') ? next : null;
}

// One delegated Bootstrap tooltip covers every page: seats show their .seat-tooltip,
// and anything else marked data-bs-toggle="tooltip" shows its data-bs-title.
document.addEventListener('DOMContentLoaded', function () {
  if (!window.bootstrap) {
    return;
  }
  new bootstrap.Tooltip(document.body, {
    selector: '[data-bs-toggle="tooltip"], .s, .layout-seat',
    html: true,
    title: function (element) {
      var tooltip = seatTooltip(element);
      // this function overrides data-bs-title, so read it here
      return tooltip ? tooltip.innerHTML : element.getAttribute('data-bs-title');
    },
  });
});

// Photos stay hidden over the placeholder until they've loaded (see .photo in style.css), including
// those in tooltips, which Bootstrap copies in as they're shown. Load events don't bubble: capture them.
document.addEventListener('load', function (event) {
  var img = event.target;
  if (img.tagName === 'IMG' && img.parentElement && img.parentElement.classList.contains('photo')) {
    img.classList.add('loaded');
  }
}, true);
