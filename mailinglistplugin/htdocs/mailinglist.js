jQuery(function($){
    $('.moreinfo,.lessinfo').click(function(e) {
        $(this).toggleClass('moreinfo lessinfo')
        $(this).closest('tr').next().toggleClass('hidden');
        return false;
    })
    $('a.subscribe').click(function(e) {
        $(this).closest('form').submit();
        return false;
    })
    
})
