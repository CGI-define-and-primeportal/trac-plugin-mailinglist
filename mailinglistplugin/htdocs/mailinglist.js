jQuery(function($){
    $('.moreinfo').click(function(e) {
      $("i", this).toggleClass("fa fa-expand fa-compress");
      $(this).closest('tr').next().toggleClass('hidden');
      $("span", this).text($("span", this).text() == "More info" ? "Less Info" : "More info");
      if($(this).hasClass("last-row")) $(this).closest("tr").toggleClass("last-row");
    });
    $('a.subscribe').click(function(e) {
        $(this).closest('form').submit();
        return false;
    })
    $(".viewinfo").click(function(e){
      e.preventDefault();
    	var parent = $(this).closest('div').parent();
    	parent.next('.information').toggleClass('hidden');
    	
    });
    $(".morebody").click(function(e){
    	$(this).next('pre').toggleClass('hidden');
    });
    $("#subscribe-link").click(function(){
      $("#subscribe-form").submit()
    });

})
