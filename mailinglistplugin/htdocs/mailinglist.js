jQuery(function($){
    $('a.moreinfo').click(function(e){
        $(this).parent().parent().next().toggleClass('hidden');
        return false;
    })
    $('a.morebody').click(function(e){
        $(this).next().toggleClass('hidden');
        return false;
    })
})
