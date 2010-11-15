jQuery(function($){
    $('a.moreinfo').click(function(e){
        $(this).parent().parent().next().toggleClass('hidden');
        return false;
    })
})
