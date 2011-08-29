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
    $(".viewinfo").click(function(e){
    	var parent = $(this).closest('div').parent().parent();
    	parent.next('.information').toggleClass('hidden');
    	
    });
    $(".morebody").click(function(e){
    	$(this).next('pre').toggleClass('hidden');
    });
})
